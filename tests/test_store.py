"""Tests for SQLite persistence backing."""

import json
from pathlib import Path

import pytest
import pytest_asyncio
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from finding_extractor.models import (
    ExamInfo,
    ExtractedFinding,
    FindingAttribute,
    FindingLocation,
    NonFindingText,
    ReportExtraction,
    ValidationResult,
)
from finding_extractor.store import (
    CorrectionRow,
    ExtractionRow,
    ExtractionStore,
)


@pytest_asyncio.fixture
async def store(tmp_path: Path):
    """Create a temporary SQLite-backed store."""
    db_path = tmp_path / "test.sqlite3"
    s = ExtractionStore(db_path)
    await s.init()
    try:
        yield s
    finally:
        await s.close()


@pytest.mark.asyncio
async def test_upsert_report_deduplicates_by_hash(store: ExtractionStore):
    """Same report text should map to a single persisted report row."""
    report_text = "Findings: No focal airspace opacity."

    first = await store.upsert_report(report_text, source_ref="report-a.md")
    second = await store.upsert_report(report_text, source_ref="report-b.md")

    assert first.id == second.id
    assert first.seen_before is False
    assert second.seen_before is True


@pytest.mark.asyncio
async def test_create_extraction_persists_payload_json(store: ExtractionStore):
    """Extraction payload is stored as JSON with nested findings and non-finding segments."""
    report = await store.upsert_report("Technique: CT.\nStone in right kidney.")
    extraction = ReportExtraction(
        exam_info=ExamInfo(
            study_description="CT Abdomen",
            study_date="2021-08-26",
            modality="CT",
            body_part="abdomen",
        ),
        findings=[
            ExtractedFinding(
                finding_name="renal calculus",
                presence="present",
                location=FindingLocation(
                    body_region="abdomen",
                    specific_anatomy="right kidney",
                    laterality="right",
                ),
                attributes=[FindingAttribute(key="size", value="3 mm")],
                report_text="Stone in right kidney.",
            ),
        ],
        non_finding_text=[
            NonFindingText(text="Technique: CT.", category="technique"),
        ],
    )

    extraction_record = await store.create_extraction(
        report_id=report.id,
        extraction=extraction,
        model_name="openai:gpt-5-mini",
        reasoning_effort="medium",
    )

    async with AsyncSession(store.engine) as session:
        row = (
            await session.exec(select(ExtractionRow).where(ExtractionRow.id == extraction_record.id))
        ).first()

    assert row is not None
    payload = json.loads(row.extraction_json)
    assert payload["exam_info"]["study_description"] == "CT Abdomen"
    assert len(payload["findings"]) == 1
    assert payload["findings"][0]["finding_name"] == "renal calculus"
    assert payload["findings"][0]["attributes"][0]["key"] == "size"
    assert len(payload["non_finding_text"]) == 1


@pytest.mark.asyncio
async def test_record_correction_supports_comment_and_addition(store: ExtractionStore):
    """Corrections can be comments or proposed new findings."""
    report = await store.upsert_report("No pleural effusion.")
    extraction = await store.create_extraction(
        report_id=report.id,
        extraction=ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[],
            non_finding_text=[],
        ),
        model_name="openai:gpt-5-mini",
    )

    comment_correction = await store.record_correction(
        extraction_id=extraction.id,
        correction_type="comment",
        comment="Double-check whether this was compared to prior imaging.",
        created_by="reviewer@example.org",
    )
    add_correction = await store.record_correction(
        extraction_id=extraction.id,
        correction_type="add_finding",
        proposed_finding=ExtractedFinding(
            finding_name="pleural effusion",
            presence="absent",
            report_text="No pleural effusion.",
        ),
        created_by="reviewer@example.org",
    )

    rows = await store.list_corrections(extraction.id)
    types = [r.correction_type for r in rows]

    assert comment_correction.id != add_correction.id
    assert len(rows) == 2
    assert "comment" in types
    assert "add_finding" in types
    assert comment_correction.comment == "Double-check whether this was compared to prior imaging."


@pytest.mark.asyncio
async def test_record_update_correction_by_finding_index(store: ExtractionStore):
    """Update correction can target a finding via finding index/path."""
    report = await store.upsert_report("Pneumonia in right lower lobe.")
    extraction = await store.create_extraction(
        report_id=report.id,
        extraction=ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[
                ExtractedFinding(
                    finding_name="pneumonia",
                    presence="present",
                    report_text="Pneumonia in right lower lobe.",
                )
            ],
            non_finding_text=[],
        ),
        model_name="openai:gpt-5-mini",
    )

    correction = await store.record_correction(
        extraction_id=extraction.id,
        correction_type="update_finding",
        target_finding_index=0,
        attribute_overrides={"severity": "mild"},
        created_by="reviewer@example.org",
    )
    assert correction.target_finding_index == 0
    assert correction.target_json_path == "$.findings[0]"

    async with AsyncSession(store.engine) as session:
        row = (await session.exec(select(CorrectionRow).where(CorrectionRow.id == correction.id))).first()
    assert row is not None
    assert row.target_json_path == "$.findings[0]"


@pytest.mark.asyncio
async def test_get_report_and_list_reports(store: ExtractionStore):
    """Report read APIs return detail and paginated summary objects."""
    first = await store.upsert_report("First report", source_ref="first.md")
    second = await store.upsert_report("Second report", source_ref="second.md")

    got_first = await store.get_report(first.id)
    assert got_first is not None
    assert got_first.id == first.id
    assert got_first.report_text == "First report"

    listed = await store.list_reports(limit=10, offset=0)
    listed_ids = {item.id for item in listed}
    assert first.id in listed_ids
    assert second.id in listed_ids


@pytest.mark.asyncio
async def test_get_extraction_and_list_extractions(store: ExtractionStore):
    """Extraction read APIs deserialize payloads and filter by report."""
    report = await store.upsert_report("Test report text")
    other_report = await store.upsert_report("Other report text")

    extraction = ReportExtraction(
        exam_info=ExamInfo(study_description="CT Abdomen", modality="CT", body_part="abdomen"),
        findings=[
            ExtractedFinding(
                finding_name="renal calculus",
                presence="present",
                report_text="Stone in the right kidney.",
            )
        ],
        non_finding_text=[NonFindingText(text="Technique: CT.", category="technique")],
    )
    validation = ValidationResult(
        is_valid=True,
        verbatim_errors=[],
        coverage_warnings=[],
    )

    first = await store.create_extraction(
        report_id=report.id,
        extraction=extraction,
        model_name="openai:gpt-5-mini",
        validation_result=validation,
    )
    _ = await store.create_extraction(
        report_id=other_report.id,
        extraction=ReportExtraction(exam_info=ExamInfo(study_description="Chest XR")),
        model_name="openai:gpt-5-mini",
    )

    detail = await store.get_extraction(first.id)
    assert detail is not None
    assert detail.id == first.id
    assert detail.extraction.exam_info.study_description == "CT Abdomen"
    assert detail.validation_result is not None
    assert detail.validation_result.is_valid is True

    listed = await store.list_extractions(report.id)
    assert [item.id for item in listed] == [first.id]


@pytest.mark.asyncio
async def test_job_lifecycle_round_trip(store: ExtractionStore):
    """Jobs can be created, transitioned, and fetched by polling APIs."""
    report = await store.upsert_report("Pending report")
    job = await store.create_job(job_id="job-1", report_id=report.id, status="pending")
    assert job.status == "pending"

    await store.mark_job_running("job-1")
    running = await store.get_job("job-1")
    assert running is not None
    assert running.status == "running"
    assert running.started_at is not None

    extraction = await store.create_extraction(
        report_id=report.id,
        extraction=ReportExtraction(exam_info=ExamInfo(study_description="CT")),
        model_name="openai:gpt-5-mini",
    )
    await store.mark_job_completed("job-1", extraction_id=extraction.id)
    completed = await store.get_job("job-1")
    assert completed is not None
    assert completed.status == "completed"
    assert completed.extraction_id == extraction.id
    assert completed.completed_at is not None


@pytest.mark.asyncio
async def test_mark_job_failed_records_error(store: ExtractionStore):
    """Failed jobs expose an error string and completion timestamp."""
    report = await store.upsert_report("Failed report")
    await store.create_job(job_id="job-2", report_id=report.id)

    await store.mark_job_failed("job-2", error="boom")
    failed = await store.get_job("job-2")
    assert failed is not None
    assert failed.status == "failed"
    assert failed.error == "boom"
    assert failed.completed_at is not None


@pytest.mark.asyncio
async def test_sqlite_pragmas_are_applied(store: ExtractionStore):
    """Connections enforce SQLite WAL and related concurrency settings."""
    async with store.engine.connect() as conn:
        journal_mode = (await conn.exec_driver_sql("PRAGMA journal_mode")).scalar()
        busy_timeout = (await conn.exec_driver_sql("PRAGMA busy_timeout")).scalar()
        synchronous = (await conn.exec_driver_sql("PRAGMA synchronous")).scalar()
        foreign_keys = (await conn.exec_driver_sql("PRAGMA foreign_keys")).scalar()

    assert str(journal_mode).lower() == "wal"
    assert busy_timeout == 5000
    # NORMAL can be returned as either integer (1) or string.
    assert str(synchronous).lower() in {"1", "normal"}
    assert foreign_keys == 1
