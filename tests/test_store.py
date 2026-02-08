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
