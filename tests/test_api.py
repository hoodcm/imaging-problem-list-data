"""Tests for FastAPI server endpoints and async extraction dispatch."""

from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio
import taskiq_fastapi
from httpx import ASGITransport, AsyncClient
from taskiq import InMemoryBroker

from finding_extractor.api import create_app
from finding_extractor.models import ExamInfo, ExtractedFinding, ReportExtraction
from finding_extractor.store import ExtractionStore


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    """Create a temporary SQLite-backed store for API tests."""
    db_path = tmp_path / "api.sqlite3"
    s = ExtractionStore(db_path)
    await s.init()
    try:
        yield s
    finally:
        await s.close()


@pytest.fixture
def broker() -> InMemoryBroker:
    """In-memory TaskIQ broker for deterministic tests."""
    return InMemoryBroker(await_inplace=True)


@pytest_asyncio.fixture
async def app(store: ExtractionStore, broker: InMemoryBroker):
    """Create FastAPI app wired to temp store + in-memory broker."""
    app = create_app(store=store, broker=broker)
    taskiq_fastapi.populate_dependency_context(broker, app)
    try:
        yield app
    finally:
        broker.custom_dependency_context = {}


@pytest_asyncio.fixture
async def client(app):
    """Async HTTP client over ASGI transport."""
    async with app.router.lifespan_context(app), AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as c:
        yield c


def _fake_extraction(study_description: str = "Chest XR") -> ReportExtraction:
    """Stable extraction payload used in API tests."""
    return ReportExtraction(
        exam_info=ExamInfo(study_description=study_description, modality="XR", body_part="chest"),
        findings=[
            ExtractedFinding(
                finding_name="pleural effusion",
                presence="absent",
                report_text="No pleural effusion.",
            )
        ],
        non_finding_text=[],
    )


@pytest.mark.asyncio
async def test_healthz_and_readyz(client: AsyncClient):
    """Health/readiness probes should return healthy status payloads."""
    health = await client.get("/api/healthz")
    ready = await client.get("/api/readyz")

    assert health.status_code == 200
    assert health.json() == {"status": "ok"}
    assert ready.status_code == 200
    assert ready.json() == {"status": "ready"}


@pytest.mark.asyncio
async def test_report_submit_and_dedupe(client: AsyncClient):
    """POST /api/reports upserts by text hash and toggles seen_before."""
    payload = {"report_text": "No pleural effusion.", "source_ref": "report-a.txt"}
    first = await client.post("/api/reports", json=payload)
    second = await client.post("/api/reports", json={"report_text": "No pleural effusion."})

    assert first.status_code == 200
    assert second.status_code == 200
    first_body = first.json()
    second_body = second.json()
    assert first_body["id"] == second_body["id"]
    assert first_body["seen_before"] is False
    assert second_body["seen_before"] is True


@pytest.mark.asyncio
async def test_report_list_and_detail(client: AsyncClient):
    """GET report list/detail returns persisted report content."""
    created = await client.post("/api/reports", json={"report_text": "Technique: CT."})
    report_id = created.json()["id"]

    listed = await client.get("/api/reports")
    detail = await client.get(f"/api/reports/{report_id}")

    assert listed.status_code == 200
    assert any(item["id"] == report_id for item in listed.json())
    assert detail.status_code == 200
    assert detail.json()["report_text"] == "Technique: CT."


@pytest.mark.asyncio
async def test_report_detail_not_found(client: AsyncClient):
    """GET /api/reports/{id} returns 404 for missing report."""
    response = await client.get("/api/reports/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_extract_dispatch_job_and_extraction_reads(client: AsyncClient, monkeypatch):
    """Dispatch endpoint creates job and extraction rows, then read endpoints return them."""

    async def fake_extract_findings(report_text, exam_description=None, model=None, reasoning=None):
        _ = (report_text, exam_description, model, reasoning)
        return _fake_extraction("Chest XR")

    monkeypatch.setattr("finding_extractor.tasks.extract_findings", fake_extract_findings)

    report = await client.post("/api/reports", json={"report_text": "No pleural effusion."})
    report_id = report.json()["id"]

    dispatch = await client.post(f"/api/reports/{report_id}/extract", json={})
    assert dispatch.status_code == 202
    assert dispatch.headers["Location"].startswith("/api/jobs/")
    job_id = dispatch.json()["job_id"]

    job = await client.get(f"/api/jobs/{job_id}")
    assert job.status_code == 200
    assert job.json()["status"] in {"pending", "running", "completed"}

    # await_inplace=True should complete this quickly.
    job_final = await client.get(f"/api/jobs/{job_id}")
    assert job_final.status_code == 200
    assert job_final.json()["status"] == "completed"
    extraction_id = job_final.json()["extraction_id"]
    assert extraction_id is not None

    extractions = await client.get(f"/api/reports/{report_id}/extractions")
    assert extractions.status_code == 200
    assert len(extractions.json()) == 1
    assert extractions.json()[0]["id"] == extraction_id

    extraction_detail = await client.get(f"/api/extractions/{extraction_id}")
    assert extraction_detail.status_code == 200
    assert extraction_detail.json()["extraction"]["findings"][0]["finding_name"] == "pleural effusion"


@pytest.mark.asyncio
async def test_extract_dispatch_not_found(client: AsyncClient):
    """POST /api/reports/{id}/extract returns 404 for unknown report."""
    response = await client.post("/api/reports/missing/extract", json={})
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_extract_dispatch_enqueue_failure_marks_job_failed(
    app,
    client: AsyncClient,
    monkeypatch,
):
    """Enqueue failures should return 503 and mark job as failed (not stuck pending)."""

    async def fail_kiq(*args, **kwargs):
        _ = (args, kwargs)
        raise RuntimeError("queue down")

    report = await client.post("/api/reports", json={"report_text": "No focal consolidation."})
    report_id = report.json()["id"]

    monkeypatch.setattr(app.state.run_extraction_task, "kiq", fail_kiq)
    monkeypatch.setattr("finding_extractor.api.uuid4", lambda: UUID("00000000-0000-0000-0000-000000000123"))

    dispatch = await client.post(f"/api/reports/{report_id}/extract", json={})
    assert dispatch.status_code == 503

    job = await client.get("/api/jobs/00000000-0000-0000-0000-000000000123")
    assert job.status_code == 200
    assert job.json()["status"] == "failed"
    assert job.json()["error"] == "enqueue_failed:queue_unavailable"


@pytest.mark.asyncio
async def test_job_not_found(client: AsyncClient):
    """GET /api/jobs/{id} returns 404 for unknown job."""
    response = await client.get("/api/jobs/does-not-exist")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_extraction_detail_not_found(client: AsyncClient):
    """GET /api/extractions/{id} returns 404 when extraction is absent."""
    response = await client.get("/api/extractions/missing")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_and_list_corrections(store: ExtractionStore, client: AsyncClient):
    """Correction create/list endpoints persist and return correction rows."""
    report = await store.upsert_report("No pleural effusion.")
    extraction = await store.create_extraction(
        report_id=report.id,
        extraction=_fake_extraction(),
        model_name="openai:gpt-5-mini",
    )

    create_payload = {
        "correction_type": "comment",
        "comment": "Looks good",
        "created_by": "reviewer@example.org",
    }
    created = await client.post(
        f"/api/extractions/{extraction.id}/corrections",
        json=create_payload,
    )
    listed = await client.get(f"/api/extractions/{extraction.id}/corrections")

    assert created.status_code == 201
    assert created.json()["comment"] == "Looks good"
    assert listed.status_code == 200
    assert len(listed.json()) == 1
    assert listed.json()[0]["correction_type"] == "comment"
    assert listed.json()[0]["comment"] == "Looks good"


@pytest.mark.asyncio
async def test_corrections_not_found(client: AsyncClient):
    """Correction endpoints return 404 for unknown extraction ids."""
    create = await client.post(
        "/api/extractions/missing/corrections",
        json={"correction_type": "comment", "comment": "test"},
    )
    listed = await client.get("/api/extractions/missing/corrections")
    assert create.status_code == 404
    assert listed.status_code == 404
