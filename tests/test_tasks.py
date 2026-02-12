"""Tests for TaskIQ task behavior and error handling."""

import inspect
from pathlib import Path

import pytest
import pytest_asyncio
from structlog.contextvars import get_contextvars
from taskiq.state import TaskiqState

from finding_extractor.broker import configure_worker_observability
from finding_extractor.store import ExtractionStore
from finding_extractor.tasks import _run_extraction_impl


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
