"""Tests for TaskIQ task behavior and error handling."""

from pathlib import Path

import pytest
import pytest_asyncio

from finding_extractor.store import ExtractionStore
from finding_extractor.tasks import _run_extraction_impl


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    """Create a temporary SQLite-backed store for task tests."""
    db_path = tmp_path / "tasks.sqlite3"
    s = ExtractionStore(db_path)
    await s.init()
    try:
        yield s
    finally:
        await s.close()


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
