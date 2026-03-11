"""Report persistence helpers and public report return types."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlmodel import col, select

from finding_extractor.db.engine import StoreRuntime
from finding_extractor.db.tables import ReportRow
from finding_extractor.extractor.report_sections import parse_report_sections, sections_to_json


@dataclass(frozen=True)
class StoredReport:
    """A persisted source report."""

    id: str
    text_hash: str
    source_ref: str | None
    patient_id: str | None
    created_at: str
    seen_before: bool = False


@dataclass(frozen=True)
class StoredReportDetail:
    """A persisted source report with body text."""

    id: str
    text_hash: str
    report_text: str
    source_ref: str | None
    patient_id: str | None
    created_at: str


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _hash_report_text(report_text: str) -> str:
    return hashlib.sha256(report_text.encode("utf-8")).hexdigest()


def _stored_report_from_row(row: ReportRow, *, seen_before: bool = False) -> StoredReport:
    return StoredReport(
        id=row.id,
        text_hash=row.text_hash,
        source_ref=row.source_ref,
        patient_id=row.patient_id,
        created_at=row.created_at,
        seen_before=seen_before,
    )


def _stored_report_detail_from_row(row: ReportRow) -> StoredReportDetail:
    return StoredReportDetail(
        id=row.id,
        text_hash=row.text_hash,
        report_text=row.report_text,
        source_ref=row.source_ref,
        patient_id=row.patient_id,
        created_at=row.created_at,
    )


async def upsert_report(
    runtime: StoreRuntime,
    report_text: str,
    source_ref: str | None = None,
    patient_id: str | None = None,
) -> StoredReport:
    """Insert report if unseen, otherwise return existing record."""
    text_hash = _hash_report_text(report_text)

    async with runtime.session() as session:
        existing = (
            await session.exec(select(ReportRow).where(ReportRow.text_hash == text_hash))
        ).first()
        if existing is not None:
            updated = False
            if source_ref and not existing.source_ref:
                existing.source_ref = source_ref
                updated = True
            if patient_id and not existing.patient_id:
                existing.patient_id = patient_id
                updated = True
            if existing.section_structure_json is None:
                parsed = parse_report_sections(report_text)
                serialized = sections_to_json(parsed.sections)
                if serialized is not None:
                    existing.section_structure_json = serialized
                    updated = True
            if updated:
                session.add(existing)
                await session.commit()
                await session.refresh(existing)
            return _stored_report_from_row(existing, seen_before=True)

        parsed = parse_report_sections(report_text)
        report_row = ReportRow(
            id=str(uuid4()),
            text_hash=text_hash,
            report_text=report_text,
            source_ref=source_ref,
            patient_id=patient_id,
            section_structure_json=sections_to_json(parsed.sections),
            created_at=_utc_now_iso(),
        )
        session.add(report_row)
        await session.commit()
        return _stored_report_from_row(report_row)


async def get_report(runtime: StoreRuntime, report_id: str) -> StoredReportDetail | None:
    """Fetch one report including report text."""
    async with runtime.session() as session:
        row = (await session.exec(select(ReportRow).where(ReportRow.id == report_id))).first()
    if row is None:
        return None
    return _stored_report_detail_from_row(row)


async def list_reports(
    runtime: StoreRuntime, limit: int = 50, offset: int = 0
) -> list[StoredReport]:
    """List reports (without report text) with pagination."""
    async with runtime.session() as session:
        rows = (
            await session.exec(
                select(ReportRow)
                .order_by(col(ReportRow.created_at).desc(), col(ReportRow.id).desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
    return [_stored_report_from_row(row) for row in rows]
