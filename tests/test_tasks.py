"""Tests for TaskIQ task behavior and error handling."""

import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from pydantic_ai.exceptions import FallbackExceptionGroup, ModelHTTPError, UnexpectedModelBehavior
from structlog.contextvars import get_contextvars
from taskiq.state import TaskiqState

from finding_extractor.broker import (
    cleanup_worker_coding_resources,
    configure_worker_observability,
)
from finding_extractor.config import Settings
from finding_extractor.extraction_orchestrator import format_stage_status
from finding_extractor.models import ValidationResult
from finding_extractor.store import ExtractionStore
from finding_extractor.tasks import (
    ReliabilityContractError,
    _run_extraction_impl,
    to_public_job_error,
)


@pytest_asyncio.fixture
async def store(tmp_path: Path, store_factory):
    """Create a temporary SQLite-backed store for task tests."""
    async with store_factory(tmp_path / "tasks.sqlite3") as s:
        yield s


def _settings_for_test(**overrides) -> Settings:
    """Build a typed settings object for task tests."""
    return Settings.model_construct(
        db_path=Path(".finding_extractor.db"),
        redis_url="redis://localhost:6379",
        default_model="openai:gpt-5-mini",
        **overrides,
    )


@pytest.mark.asyncio
async def test_run_extraction_impl_sanitizes_task_error(store: ExtractionStore, monkeypatch):
    """Task failures should store a stable, non-sensitive public error string."""

    async def fake_extract_findings(*args, **kwargs):
        _ = (args, kwargs)
        raise RuntimeError("leaked-secret sk-proj-should-not-appear")

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)

    report = await store.upsert_report("FINDINGS: No pleural effusion.")
    await store.create_job(job_id="job-sanitize", report_id=report.id)

    with pytest.raises(RuntimeError):
        await _run_extraction_impl(job_id="job-sanitize", report_id=report.id, store=store)

    job = await store.get_job("job-sanitize")
    assert job is not None
    assert job.status == "failed"
    assert job.error == "extraction_failed:internal_error"
    assert "sk-proj" not in (job.error or "")


def test_to_public_job_error_uses_typed_exception_mapping():
    """Public error mapping should use typed PydanticAI exceptions."""
    provider_err = ModelHTTPError(status_code=429, model_name="openai:gpt-5-mini")
    validation_err = UnexpectedModelBehavior("validation failed")

    assert to_public_job_error(provider_err) == "extraction_failed:model_provider_error"
    assert to_public_job_error(validation_err) == "extraction_failed:model_output_validation_failed"


def test_to_public_job_error_maps_fallback_group_provider_failures():
    """Fallback exhaustion with provider errors should map to provider error code."""
    provider_err = ModelHTTPError(status_code=503, model_name="openai:gpt-5-mini")
    fallback_exc = FallbackExceptionGroup("all failed", [provider_err])

    assert to_public_job_error(fallback_exc) == "extraction_failed:model_provider_error"


def test_to_public_job_error_maps_fallback_group_timeouts():
    """Fallback exhaustion with timeout-only failures should map to timeout code."""
    fallback_exc = FallbackExceptionGroup(
        "all failed",
        [TimeoutError("primary timeout"), TimeoutError("fallback timeout")],
    )

    assert to_public_job_error(fallback_exc) == "extraction_failed:model_timeout"


@pytest.mark.asyncio
async def test_run_extraction_impl_keeps_whitespace_equivalent_verbatim_segments(
    store: ExtractionStore, monkeypatch
):
    """Task-level post-filter should preserve findings that only differ by whitespace formatting."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    async def fake_extract_findings(*args, **kwargs):
        _ = (args, kwargs)
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="Chest XR"),
                findings=[
                    ExtractedFinding(
                        finding_name="atelectasis",
                        presence="present",
                        report_text="Mild\n  bibasilar   atelectasis.",
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)

    report = await store.upsert_report("Findings: Mild bibasilar atelectasis.")
    await store.create_job(job_id="job-whitespace-verbatim", report_id=report.id)

    await _run_extraction_impl(
        job_id="job-whitespace-verbatim",
        report_id=report.id,
        store=store,
    )

    job = await store.get_job("job-whitespace-verbatim")
    assert job is not None
    assert job.status == "completed"
    assert job.warning_payload is None
    assert job.extraction_id is not None
    extraction = await store.get_extraction(job.extraction_id)
    assert extraction is not None
    assert len(extraction.extraction.findings) == 1


@pytest.mark.asyncio
async def test_run_extraction_impl_completed_job_has_status_message(
    store: ExtractionStore, monkeypatch
):
    """Completed job should end with canonical completion status_message."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    intermediate_messages: list[str] = []

    async def fake_extract_findings(*args, **kwargs):
        # Invoke the status_callback that the task wires up
        status_callback = kwargs.get("status_callback")
        if status_callback is not None:
            await status_callback("Calling model...")
            intermediate_messages.append("Calling model...")
            await status_callback("Model call complete, processing results")
            intermediate_messages.append("Model call complete, processing results")
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="Chest XR"),
                findings=[
                    ExtractedFinding(
                        finding_name="pleural effusion",
                        presence="absent",
                        report_text="No pleural effusion.",
                    )
                ],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)

    report = await store.upsert_report("FINDINGS: No pleural effusion.")
    await store.create_job(job_id="job-status-msg", report_id=report.id)

    await _run_extraction_impl(job_id="job-status-msg", report_id=report.id, store=store)

    # Verify agent-emitted messages were passed through the callback
    assert "Calling model..." in intermediate_messages
    assert "Model call complete, processing results" in intermediate_messages

    job = await store.get_job("job-status-msg")
    assert job is not None
    assert job.status == "completed"
    assert job.status_message == "[stage:completed] extraction_complete"


@pytest.mark.asyncio
async def test_run_extraction_impl_emits_canonical_stage_statuses(
    store: ExtractionStore, monkeypatch
):
    """Worker run should emit canonical stage statuses in deterministic order."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    async def fake_extract_findings(*args, **kwargs):
        status_callback = kwargs.get("status_callback")
        if status_callback is not None:
            await status_callback("Calling model...")
            await status_callback("Model call complete, processing results")
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="Chest XR"),
                findings=[
                    ExtractedFinding(
                        finding_name="pleural effusion",
                        presence="absent",
                        report_text="No pleural effusion.",
                    )
                ],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)

    observed_messages: list[str] = []
    original_update = store.update_job_status_message

    async def capture_status(job_id: str, message: str) -> None:
        observed_messages.append(message)
        await original_update(job_id, message)

    monkeypatch.setattr(store, "update_job_status_message", capture_status)

    report = await store.upsert_report("FINDINGS: No pleural effusion.")
    await store.create_job(job_id="job-stage-order", report_id=report.id)
    await _run_extraction_impl(job_id="job-stage-order", report_id=report.id, store=store)

    expected_substrings = [
        format_stage_status("preflight", "retrieving_report"),
        format_stage_status("preflight", "validating_model_configuration"),
        "[stage:sectionize] ",
        format_stage_status("extract_sections", "start"),
        "[stage:extract_sections] unit=",
        "status=calling_model",
        "status=model_call_complete",
        "[stage:merge_dedupe] ",
        format_stage_status("validate_output", "validating_extraction_results"),
        format_stage_status("persist", "saving_extraction_results"),
        format_stage_status("completed", "extraction_complete"),
    ]

    cursor = 0
    for expected in expected_substrings:
        idx = next((i for i in range(cursor, len(observed_messages)) if expected in observed_messages[i]), -1)
        if idx == -1:
            raise AssertionError(f"Missing status message containing: {expected}")
        cursor = idx + 1


@pytest.mark.asyncio
async def test_run_extraction_impl_modular_pipeline_retries_only_failed_section(
    store: ExtractionStore, monkeypatch
):
    """Task wiring should enable modular mode and retry only the failed section unit."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    attempts_by_header: dict[str, int] = {}

    async def fake_extract_findings(*args, **kwargs):
        _ = args
        section_text = kwargs["report_text"]
        header = section_text.splitlines()[0].strip()
        attempts_by_header[header] = attempts_by_header.get(header, 0) + 1
        if "nephrolithiasis" in header and attempts_by_header[header] == 1:
            raise TimeoutError("first pass timeout")

        finding_text = section_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text.lower().replace(" ", "_"),
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: _settings_for_test(
            coding_enabled=False,
            extractor_max_subagent_concurrency=2,
            extractor_chunk_repair_enabled=True,
        ),
    )

    report = await store.upsert_report(
        "Findings:\nStable 3 mm right renal stone.\n"
        "Impression:\nPersistent right nephrolithiasis."
    )
    await store.create_job(job_id="job-modular-retry", report_id=report.id)

    await _run_extraction_impl(job_id="job-modular-retry", report_id=report.id, store=store)

    assert attempts_by_header["Stable 3 mm right renal stone."] == 1
    assert attempts_by_header["Persistent right nephrolithiasis."] == 2

    job = await store.get_job("job-modular-retry")
    assert job is not None
    assert job.status == "completed"
    assert job.extraction_id is not None

    extraction = await store.get_extraction(job.extraction_id)
    assert extraction is not None
    assert len(extraction.extraction.findings) == 2


@pytest.mark.asyncio
async def test_run_extraction_impl_modular_lenient_mode_completes_with_coverage_warning_payload(
    store: ExtractionStore, monkeypatch
):
    """Lenient mode should complete_with_warnings when modular repair leaves failed units."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    attempts_by_header: dict[str, int] = {}

    async def fake_extract_findings(*args, **kwargs):
        _ = args
        section_text = kwargs["report_text"]
        header = section_text.splitlines()[0].strip()
        attempts_by_header[header] = attempts_by_header.get(header, 0) + 1
        if "nephrolithiasis" in header:
            raise TimeoutError("persistent failure")

        finding_text = section_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name="right_renal_stone",
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: _settings_for_test(
            coding_enabled=False,
            extractor_max_subagent_concurrency=2,
            extractor_chunk_repair_enabled=True,
        ),
    )

    report = await store.upsert_report(
        "Findings:\nStable 3 mm right renal stone.\n"
        "Impression:\nPersistent right nephrolithiasis."
    )
    await store.create_job(job_id="job-modular-lenient-gap", report_id=report.id)

    await _run_extraction_impl(
        job_id="job-modular-lenient-gap",
        report_id=report.id,
        store=store,
        reliability_mode="lenient",
    )

    assert attempts_by_header["Stable 3 mm right renal stone."] == 1
    assert attempts_by_header["Persistent right nephrolithiasis."] == 2

    job = await store.get_job("job-modular-lenient-gap")
    assert job is not None
    assert job.status == "completed_with_warnings"
    assert job.warning_payload is not None
    assert job.warning_payload.reliability_mode == "lenient"
    assert job.warning_payload.reason_categories == ["coverage_gap"]
    assert job.warning_payload.coverage_warning_count == 1
    assert job.warning_payload.section_failure_count == 1
    assert job.extraction_id is not None

    extraction = await store.get_extraction(job.extraction_id)
    assert extraction is not None
    assert len(extraction.extraction.findings) == 1


@pytest.mark.asyncio
async def test_run_extraction_impl_lenient_warnings_emit_reliability_outcome_log(
    store: ExtractionStore, monkeypatch, context_capture_logger
):
    """Lenient warnings should emit reliability outcome telemetry with counters."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    async def fake_extract_findings(*args, **kwargs):
        _ = args
        section_text = kwargs["report_text"]
        header = section_text.splitlines()[0].strip()
        if "nephrolithiasis" in header:
            raise TimeoutError("persistent failure")

        finding_text = section_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name="right_renal_stone",
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.logger", context_capture_logger)
    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: _settings_for_test(
            coding_enabled=False,
            extractor_max_subagent_concurrency=2,
            extractor_chunk_repair_enabled=True,
        ),
    )

    report = await store.upsert_report(
        "Findings:\nStable 3 mm right renal stone.\n"
        "Impression:\nPersistent right nephrolithiasis."
    )
    await store.create_job(job_id="job-lenient-metrics", report_id=report.id)

    await _run_extraction_impl(
        job_id="job-lenient-metrics",
        report_id=report.id,
        store=store,
        reliability_mode="lenient",
    )

    outcomes = [
        record
        for record in context_capture_logger.records
        if record["event"] == "Reliability contract outcome"
    ]
    assert len(outcomes) == 1
    outcome = outcomes[0]["kwargs"]
    assert outcome["terminal_status"] == "completed_with_warnings"
    assert outcome["reliability_mode"] == "lenient"
    assert outcome["public_error"] is None
    assert outcome["reason_categories"] == ["coverage_gap"]
    assert outcome["section_failure_count"] == 1


@pytest.mark.asyncio
async def test_run_extraction_impl_modular_strict_mode_fails_when_units_remain_failed(
    store: ExtractionStore, monkeypatch
):
    """Strict mode should fail when modular repair exhausts and failed units remain."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    attempts_by_header: dict[str, int] = {}

    async def fake_extract_findings(*args, **kwargs):
        _ = args
        section_text = kwargs["report_text"]
        header = section_text.splitlines()[0].strip()
        attempts_by_header[header] = attempts_by_header.get(header, 0) + 1
        if "nephrolithiasis" in header:
            raise TimeoutError("persistent failure")

        finding_text = section_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name="right_renal_stone",
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: _settings_for_test(
            coding_enabled=False,
            extractor_max_subagent_concurrency=2,
            extractor_chunk_repair_enabled=True,
        ),
    )

    report = await store.upsert_report(
        "Findings:\nStable 3 mm right renal stone.\n"
        "Impression:\nPersistent right nephrolithiasis."
    )
    await store.create_job(job_id="job-modular-strict-gap", report_id=report.id)

    with pytest.raises(ReliabilityContractError):
        await _run_extraction_impl(
            job_id="job-modular-strict-gap",
            report_id=report.id,
            store=store,
            reliability_mode="strict",
        )

    assert attempts_by_header["Stable 3 mm right renal stone."] == 1
    assert attempts_by_header["Persistent right nephrolithiasis."] == 2

    job = await store.get_job("job-modular-strict-gap")
    assert job is not None
    assert job.status == "failed"
    assert job.error == "extraction_failed:section_failures_remaining"
    assert job.warning_payload is not None
    assert job.warning_payload.reliability_mode == "strict"
    assert job.warning_payload.reason_categories == ["coverage_gap"]
    assert job.warning_payload.coverage_warning_count == 1
    assert job.warning_payload.section_failure_count == 1


@pytest.mark.asyncio
async def test_run_extraction_impl_strict_section_failure_emits_reliability_outcome_log(
    store: ExtractionStore, monkeypatch, context_capture_logger
):
    """Strict section-failure terminal should emit reliability outcome telemetry."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    async def fake_extract_findings(*args, **kwargs):
        _ = args
        section_text = kwargs["report_text"]
        header = section_text.splitlines()[0].strip()
        if "nephrolithiasis" in header:
            raise TimeoutError("persistent failure")

        finding_text = section_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name="right_renal_stone",
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.logger", context_capture_logger)
    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: _settings_for_test(
            coding_enabled=False,
            extractor_max_subagent_concurrency=2,
            extractor_chunk_repair_enabled=True,
        ),
    )

    report = await store.upsert_report(
        "Findings:\nStable 3 mm right renal stone.\n"
        "Impression:\nPersistent right nephrolithiasis."
    )
    await store.create_job(job_id="job-strict-metrics", report_id=report.id)

    with pytest.raises(ReliabilityContractError):
        await _run_extraction_impl(
            job_id="job-strict-metrics",
            report_id=report.id,
            store=store,
            reliability_mode="strict",
        )

    outcomes = [
        record
        for record in context_capture_logger.records
        if record["event"] == "Reliability contract outcome"
    ]
    assert len(outcomes) == 1
    outcome = outcomes[0]["kwargs"]
    assert outcome["terminal_status"] == "failed"
    assert outcome["reliability_mode"] == "strict"
    assert outcome["public_error"] == "extraction_failed:section_failures_remaining"
    assert outcome["reason_categories"] == ["coverage_gap"]
    assert outcome["section_failure_count"] == 1


@pytest.mark.asyncio
async def test_run_extraction_impl_strict_prioritizes_validation_error_over_section_failure(
    store: ExtractionStore, monkeypatch
):
    """If both validation and section failure exist, strict mode should report validation_failed."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    async def fake_extract_findings(*args, **kwargs):
        _ = args
        section_text = kwargs["report_text"]
        if "nephrolithiasis" in section_text.lower():
            raise TimeoutError("persistent failure")

        finding_text = section_text.strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name="right_renal_stone",
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)
    monkeypatch.setattr(
        "finding_extractor.tasks.validate_extraction",
        lambda *_: ValidationResult(
            is_valid=False,
            verbatim_errors=["invalid quote"],
            coverage_warnings=[],
        ),
    )
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: _settings_for_test(
            coding_enabled=False,
            extractor_max_subagent_concurrency=2,
            extractor_chunk_repair_enabled=True,
        ),
    )

    report = await store.upsert_report(
        "Findings:\nStable 3 mm right renal stone.\n"
        "Impression:\nPersistent right nephrolithiasis."
    )
    await store.create_job(job_id="job-modular-strict-both", report_id=report.id)

    with pytest.raises(ReliabilityContractError):
        await _run_extraction_impl(
            job_id="job-modular-strict-both",
            report_id=report.id,
            store=store,
            reliability_mode="strict",
        )

    job = await store.get_job("job-modular-strict-both")
    assert job is not None
    assert job.status == "failed"
    assert job.error == "extraction_failed:validation_failed"
    assert job.warning_payload is not None
    assert job.warning_payload.reason_categories == ["validation_failed", "coverage_gap"]
    assert job.warning_payload.validation_error_count == 1
    assert job.warning_payload.section_failure_count == 1


@pytest.mark.asyncio
async def test_run_extraction_impl_rejects_incompatible_default_reasoning(
    store: ExtractionStore, monkeypatch
):
    """Task preflight rejects provider-incompatible default reasoning before extraction."""
    monkeypatch.setenv("IPL_REASONING", "high")

    report = await store.upsert_report("FINDINGS: No pleural effusion.")
    await store.create_job(job_id="job-bad-default-reasoning", report_id=report.id)

    with pytest.raises(ValueError, match="not supported by ollama"):
        await _run_extraction_impl(
            job_id="job-bad-default-reasoning",
            report_id=report.id,
            store=store,
            model="ollama:llama4",
        )

    job = await store.get_job("job-bad-default-reasoning")
    assert job is not None
    assert job.status == "failed"
    assert job.error == "extraction_failed:invalid_request"


@pytest.mark.asyncio
async def test_run_extraction_impl_uses_effective_reasoning_for_model_call_and_persistence(
    store: ExtractionStore, monkeypatch
):
    """Task path should use resolved effective reasoning consistently."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    captured_reasoning: str | None = None

    async def fake_extract_findings(*args, **kwargs):
        nonlocal captured_reasoning
        _ = args
        captured_reasoning = kwargs.get("reasoning")
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="Chest XR"),
                findings=[
                    ExtractedFinding(
                        finding_name="pleural effusion",
                        presence="absent",
                        report_text="No pleural effusion.",
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setenv("IPL_REASONING", "low")
    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)

    report = await store.upsert_report("FINDINGS: No pleural effusion.")
    await store.create_job(job_id="job-effective-reasoning", report_id=report.id)

    await _run_extraction_impl(
        job_id="job-effective-reasoning",
        report_id=report.id,
        store=store,
        model="openai:gpt-5-mini",
    )

    assert captured_reasoning == "low"
    job = await store.get_job("job-effective-reasoning")
    assert job is not None and job.extraction_id is not None
    extraction = await store.get_extraction(job.extraction_id)
    assert extraction is not None
    assert extraction.reasoning_effort == "low"


@pytest.mark.asyncio
async def test_run_extraction_impl_rejects_disallowed_model_prefix(store: ExtractionStore):
    """Task validation rejects policy-disallowed model IDs as invalid_request."""
    report = await store.upsert_report("FINDINGS: No pleural effusion.")
    await store.create_job(job_id="job-invalid-model", report_id=report.id)

    with pytest.raises(ValueError, match="google-vertex models are not allowed"):
        await _run_extraction_impl(
            job_id="job-invalid-model",
            report_id=report.id,
            store=store,
            model="google-vertex:gemini-3-pro",
        )

    job = await store.get_job("job-invalid-model")
    assert job is not None
    assert job.status == "failed"
    assert job.error == "extraction_failed:invalid_request"


@pytest.mark.asyncio
async def test_run_extraction_impl_emits_failed_stage_status(
    store: ExtractionStore, monkeypatch
):
    """Failure paths should emit a canonical failed-stage status message."""

    async def fake_extract_findings(*args, **kwargs):
        _ = (args, kwargs)
        raise TimeoutError("provider timeout")

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)

    observed_messages: list[str] = []
    original_update = store.update_job_status_message

    async def capture_status(job_id: str, message: str) -> None:
        observed_messages.append(message)
        await original_update(job_id, message)

    monkeypatch.setattr(store, "update_job_status_message", capture_status)

    report = await store.upsert_report("FINDINGS: No pleural effusion.")
    await store.create_job(job_id="job-failed-stage", report_id=report.id)

    with pytest.raises(TimeoutError):
        await _run_extraction_impl(job_id="job-failed-stage", report_id=report.id, store=store)

    assert format_stage_status("failed", "extraction_failed:model_timeout") in observed_messages


@pytest.mark.asyncio
async def test_run_extraction_impl_binds_worker_job_context(
    store: ExtractionStore, monkeypatch, context_capture_logger
):
    """Task execution logs should include job/report contextvars and clear after run."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    monkeypatch.setattr("finding_extractor.tasks.logger", context_capture_logger)

    async def fake_extract_findings(*args, **kwargs):
        _ = (args, kwargs)
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="Chest XR"),
                findings=[
                    ExtractedFinding(
                        finding_name="pleural effusion",
                        presence="absent",
                        report_text="No pleural effusion.",
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)

    report = await store.upsert_report("FINDINGS: No pleural effusion.")
    await store.create_job(job_id="job-context", report_id=report.id)

    await _run_extraction_impl(job_id="job-context", report_id=report.id, store=store)

    task_logs = [
        record
        for record in context_capture_logger.records
        if record["event"] in {"Extraction task started", "Extraction task completed"}
    ]
    assert len(task_logs) == 2
    for record in task_logs:
        context = record["context"]
        assert context["job_id"] == "job-context"
        assert context["report_id"] == report.id
    assert get_contextvars() == {}


@pytest.mark.asyncio
async def test_worker_startup_configures_observability_once(monkeypatch, runtime_logging_spy):
    """Worker startup hook should configure logfire and logging once per process."""
    sentinel_settings = object()

    def fake_get_settings():
        return sentinel_settings

    monkeypatch.setattr("finding_extractor.broker.get_settings", fake_get_settings)
    runtime_logging_spy.patch(
        monkeypatch,
        "finding_extractor.broker",
        logfire_enabled=True,
    )

    maybe_awaitable = configure_worker_observability(TaskiqState())
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable

    assert len(runtime_logging_spy.configure_calls) == 1
    assert len(runtime_logging_spy.setup_calls) == 1
    assert runtime_logging_spy.configure_calls[0]["runtime"] == "worker"
    assert runtime_logging_spy.configure_calls[0]["enabled_override"] is None
    assert runtime_logging_spy.configure_calls[0]["fastapi_app"] is None
    assert runtime_logging_spy.setup_calls[0]["settings"] is sentinel_settings
    assert runtime_logging_spy.setup_calls[0]["include_logfire_processor"] is True


@pytest.mark.asyncio
async def test_worker_shutdown_cleans_up_reusable_coding_indexes(monkeypatch):
    """Worker shutdown hook should close reusable coding index resources."""
    called = {"count": 0}

    async def fake_close_indexes():
        called["count"] += 1

    monkeypatch.setattr("finding_extractor.broker.close_reusable_coding_indexes", fake_close_indexes)

    maybe_awaitable = cleanup_worker_coding_resources(TaskiqState())
    if inspect.isawaitable(maybe_awaitable):
        await maybe_awaitable

    assert called["count"] == 1


# ---------------------------------------------------------------------------
# Coding bridge integration tests
# ---------------------------------------------------------------------------


def _fake_extract_result():
    """Build a fake ExtractionResult for coding bridge tests."""
    from finding_extractor.models import (
        ExamInfo,
        ExtractedFinding,
        ExtractionResult,
        ReportExtraction,
    )

    return ExtractionResult(
        extraction=ReportExtraction(
            exam_info=ExamInfo(study_description="CT Abdomen"),
            findings=[
                ExtractedFinding(
                    finding_name="hepatic steatosis",
                    presence="present",
                    report_text="Hepatic steatosis.",
                ),
            ],
        ),
        usage=None,
    )


@pytest.mark.asyncio
async def test_coding_wired_when_enabled(store: ExtractionStore, monkeypatch):
    """With coding_enabled=True, inline coding is persisted in extraction_json."""
    from finding_extractor.models import FindingCode, FindingCodingBundle, LocationCode

    coded_extraction = _fake_extract_result().extraction.model_copy(
        update={
            "findings": [
                _fake_extract_result().extraction.findings[0].model_copy(
                    update={
                        "coding": FindingCodingBundle(
                            finding_code=FindingCode(
                                status="coded",
                                oifm_id="OIFM_TEST_000001",
                                oifm_name="hepatic steatosis",
                                method="exact",
                            ),
                            location_code=LocationCode(),
                        )
                    }
                )
            ]
        }
    )

    monkeypatch.setattr(
        "finding_extractor.tasks.extract_findings",
        AsyncMock(return_value=_fake_extract_result()),
    )
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: _settings_for_test(coding_enabled=True),
    )
    monkeypatch.setattr(
        "finding_extractor.code_assigner.apply_coding",
        AsyncMock(return_value=coded_extraction),
    )

    report = await store.upsert_report("FINDINGS: Hepatic steatosis.")
    await store.create_job(job_id="job-coding-on", report_id=report.id)

    await _run_extraction_impl(job_id="job-coding-on", report_id=report.id, store=store)

    # Check that inline coding was persisted in extraction_json
    async with store.session() as session:
        from sqlmodel import select

        from finding_extractor.store import ExtractionRow

        rows = (await session.exec(select(ExtractionRow))).all()
        assert len(rows) == 1
        payload = json.loads(rows[0].extraction_json)
        finding = payload["findings"][0]
        assert finding["coding"]["finding_code"]["oifm_id"] == "OIFM_TEST_000001"


@pytest.mark.asyncio
async def test_coding_skipped_when_disabled(store: ExtractionStore, monkeypatch):
    """With coding_enabled=False, findings remain uncoded."""
    monkeypatch.setattr(
        "finding_extractor.tasks.extract_findings",
        AsyncMock(return_value=_fake_extract_result()),
    )
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: _settings_for_test(coding_enabled=False),
    )

    report = await store.upsert_report("FINDINGS: Hepatic steatosis.")
    await store.create_job(job_id="job-coding-off", report_id=report.id)

    await _run_extraction_impl(job_id="job-coding-off", report_id=report.id, store=store)

    async with store.session() as session:
        from sqlmodel import select

        from finding_extractor.store import ExtractionRow

        rows = (await session.exec(select(ExtractionRow))).all()
        assert len(rows) == 1
        payload = json.loads(rows[0].extraction_json)
        assert payload["findings"][0].get("coding") is None


@pytest.mark.asyncio
async def test_coding_failure_does_not_fail_extraction(store: ExtractionStore, monkeypatch):
    """If apply_coding raises, extraction still succeeds with uncoded findings."""
    monkeypatch.setattr(
        "finding_extractor.tasks.extract_findings",
        AsyncMock(return_value=_fake_extract_result()),
    )
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: _settings_for_test(coding_enabled=True),
    )
    monkeypatch.setattr(
        "finding_extractor.code_assigner.apply_coding",
        AsyncMock(side_effect=RuntimeError("coding bridge exploded")),
    )

    report = await store.upsert_report("FINDINGS: Hepatic steatosis.")
    await store.create_job(job_id="job-coding-fail", report_id=report.id)

    await _run_extraction_impl(job_id="job-coding-fail", report_id=report.id, store=store)

    job = await store.get_job("job-coding-fail")
    assert job is not None
    assert job.status == "completed"

    async with store.session() as session:
        from sqlmodel import select

        from finding_extractor.store import ExtractionRow

        rows = (await session.exec(select(ExtractionRow))).all()
        assert len(rows) == 1
        payload = json.loads(rows[0].extraction_json)
        assert payload["findings"][0].get("coding") is None


@pytest.mark.asyncio
async def test_run_extraction_impl_lenient_mode_completes_with_warnings(store: ExtractionStore, monkeypatch):
    """Lenient mode should drop invalid spans and complete_with_warnings."""
    from finding_extractor.models import ExamInfo, ExtractionResult, ReportExtraction

    async def fake_extract_findings(*args, **kwargs):
        _ = (args, kwargs)
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="Chest XR"),
                findings=[],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)
    monkeypatch.setattr(
        "finding_extractor.tasks.validate_extraction",
        lambda *_: ValidationResult(
            is_valid=False,
            verbatim_errors=["invalid quote"],
            coverage_warnings=[],
        ),
    )

    report = await store.upsert_report("FINDINGS: No pleural effusion.")
    await store.create_job(job_id="job-lenient-warning", report_id=report.id)

    await _run_extraction_impl(
        job_id="job-lenient-warning",
        report_id=report.id,
        store=store,
        reliability_mode="lenient",
    )

    job = await store.get_job("job-lenient-warning")
    assert job is not None
    assert job.status == "completed_with_warnings"
    assert job.warning_payload is not None
    assert job.warning_payload.reliability_mode == "lenient"
    assert job.warning_payload.validation_error_count == 1
    assert job.warning_payload.section_failure_count == 0


@pytest.mark.asyncio
async def test_run_extraction_impl_strict_mode_fails_on_validation_errors(store: ExtractionStore, monkeypatch):
    """Strict mode should fail with validation_failed and warning payload."""
    from finding_extractor.models import ExamInfo, ExtractionResult, ReportExtraction

    async def fake_extract_findings(*args, **kwargs):
        _ = (args, kwargs)
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="Chest XR"),
                findings=[],
                non_finding_text=[],
            ),
            usage=None,
        )

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)
    monkeypatch.setattr(
        "finding_extractor.tasks.validate_extraction",
        lambda *_: ValidationResult(
            is_valid=False,
            verbatim_errors=["invalid quote"],
            coverage_warnings=[],
        ),
    )

    report = await store.upsert_report("FINDINGS: No pleural effusion.")
    await store.create_job(job_id="job-strict-warning", report_id=report.id)

    with pytest.raises(ReliabilityContractError):
        await _run_extraction_impl(
            job_id="job-strict-warning",
            report_id=report.id,
            store=store,
            reliability_mode="strict",
        )

    job = await store.get_job("job-strict-warning")
    assert job is not None
    assert job.status == "failed"
    assert job.error == "extraction_failed:validation_failed"
    assert job.warning_payload is not None
    assert job.warning_payload.reliability_mode == "strict"
    assert job.warning_payload.section_failure_count == 0
