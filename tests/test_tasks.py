"""Tests for TaskIQ task behavior and error handling."""

import inspect
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from structlog.contextvars import get_contextvars
from taskiq.state import TaskiqState

from finding_extractor.broker import configure_worker_observability
from finding_extractor.extraction_orchestrator import format_stage_status
from finding_extractor.models import ValidationResult
from finding_extractor.store import ExtractionStore
from finding_extractor.tasks import ReliabilityContractError, _run_extraction_impl


@pytest_asyncio.fixture
async def store(tmp_path: Path, store_factory):
    """Create a temporary SQLite-backed store for task tests."""
    async with store_factory(tmp_path / "tasks.sqlite3") as s:
        yield s


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


@pytest.mark.asyncio
async def test_run_extraction_impl_completed_job_has_status_message(
    store: ExtractionStore, monkeypatch
):
    """Completed job should have status_message set to 'Extraction complete' and agent-emitted messages should have been written during the run."""
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
    assert job.status_message == "Extraction complete"


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

    expected_in_order = [
        format_stage_status("preflight", "retrieving_report"),
        format_stage_status("preflight", "validating_model_configuration"),
        format_stage_status("sectionize", "legacy_single_pass"),
        format_stage_status("extract_sections", "start"),
        format_stage_status("extract_sections", "calling_model"),
        format_stage_status("extract_sections", "model_call_complete"),
        format_stage_status("merge_dedupe", "legacy_passthrough"),
        format_stage_status("repair_failed_sections", "legacy_noop"),
        format_stage_status("validate_output", "validating_extraction_results"),
        format_stage_status("persist", "saving_extraction_results"),
        format_stage_status("completed", "extraction_complete"),
    ]

    cursor = 0
    for expected in expected_in_order:
        try:
            idx = observed_messages.index(expected, cursor)
        except ValueError as exc:
            raise AssertionError(f"Missing status message: {expected}") from exc
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
        if header == "Impression:" and attempts_by_header[header] == 1:
            raise TimeoutError("first pass timeout")

        finding_text = section_text.splitlines()[1].strip()
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
        lambda: type(
            "S",
            (),
            {
                "default_model": "openai:gpt-5-mini",
                "coding_enabled": False,
                "modular_pipeline_enabled": True,
                "modular_pipeline_max_concurrency": 2,
                "modular_pipeline_repair_attempts": 1,
            },
        )(),
    )

    report = await store.upsert_report(
        "Findings:\nStable 3 mm right renal stone.\n"
        "Impression:\nPersistent right nephrolithiasis."
    )
    await store.create_job(job_id="job-modular-retry", report_id=report.id)

    await _run_extraction_impl(job_id="job-modular-retry", report_id=report.id, store=store)

    assert attempts_by_header["Findings:"] == 1
    assert attempts_by_header["Impression:"] == 2

    job = await store.get_job("job-modular-retry")
    assert job is not None
    assert job.status == "completed"
    assert job.extraction_id is not None

    extraction = await store.get_extraction(job.extraction_id)
    assert extraction is not None
    assert len(extraction.extraction.findings) == 2


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
    """With coding_enabled=True, coding_json is persisted on the extraction."""
    from finding_extractor.models import CodingBridgeResult, FindingCoding, LocationCoding

    fake_coding = CodingBridgeResult(
        finding_codings=[
            FindingCoding(
                oifm_id="OIFM_TEST_000001",
                oifm_name="hepatic steatosis",
                method="exact",
            )
        ],
        location_codings=[LocationCoding()],
        unresolved=[],
        coded_count=1,
        unresolved_count=0,
    )

    monkeypatch.setattr(
        "finding_extractor.tasks.extract_findings",
        AsyncMock(return_value=_fake_extract_result()),
    )
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: type("S", (), {"default_model": "openai:gpt-5-mini", "coding_enabled": True})(),
    )
    monkeypatch.setattr(
        "finding_extractor.coding_bridge.apply_coding",
        AsyncMock(return_value=fake_coding),
    )

    report = await store.upsert_report("FINDINGS: Hepatic steatosis.")
    await store.create_job(job_id="job-coding-on", report_id=report.id)

    await _run_extraction_impl(job_id="job-coding-on", report_id=report.id, store=store)

    # Check that coding_json was persisted
    async with store.session() as session:
        from sqlmodel import select

        from finding_extractor.store import ExtractionRow

        rows = (await session.exec(select(ExtractionRow))).all()
        assert len(rows) == 1
        assert rows[0].coding_json is not None
        coding_data = json.loads(rows[0].coding_json)
        assert coding_data["coded_count"] == 1


@pytest.mark.asyncio
async def test_coding_skipped_when_disabled(store: ExtractionStore, monkeypatch):
    """With coding_enabled=False (default), coding_json is None."""
    monkeypatch.setattr(
        "finding_extractor.tasks.extract_findings",
        AsyncMock(return_value=_fake_extract_result()),
    )

    report = await store.upsert_report("FINDINGS: Hepatic steatosis.")
    await store.create_job(job_id="job-coding-off", report_id=report.id)

    await _run_extraction_impl(job_id="job-coding-off", report_id=report.id, store=store)

    async with store.session() as session:
        from sqlmodel import select

        from finding_extractor.store import ExtractionRow

        rows = (await session.exec(select(ExtractionRow))).all()
        assert len(rows) == 1
        assert rows[0].coding_json is None


@pytest.mark.asyncio
async def test_coding_failure_does_not_fail_extraction(store: ExtractionStore, monkeypatch):
    """If apply_coding raises, extraction still succeeds with coding_json=None."""
    monkeypatch.setattr(
        "finding_extractor.tasks.extract_findings",
        AsyncMock(return_value=_fake_extract_result()),
    )
    monkeypatch.setattr(
        "finding_extractor.tasks.get_settings",
        lambda: type("S", (), {"default_model": "openai:gpt-5-mini", "coding_enabled": True})(),
    )
    monkeypatch.setattr(
        "finding_extractor.coding_bridge.apply_coding",
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
        assert rows[0].coding_json is None


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
