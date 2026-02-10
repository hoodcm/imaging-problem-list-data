"""Async SQLModel-backed persistence for report/extraction experiments."""

from __future__ import annotations

import hashlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import uuid4

from sqlalchemy import CheckConstraint, event
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import Field, SQLModel, col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from finding_extractor.models import ExtractedFinding, ReportExtraction, ValidationResult

CorrectionType = Literal["add_finding", "update_finding", "comment"]
CorrectionStatus = Literal["pending", "accepted", "rejected", "applied"]
JobStatus = Literal["pending", "running", "completed", "failed"]


class ReportRow(SQLModel, table=True):
    """Deduplicated source report content."""

    __tablename__ = "reports"

    id: str = Field(primary_key=True)
    text_hash: str = Field(unique=True, index=True)
    report_text: str
    source_ref: str | None = None
    created_at: str


class ExtractionRow(SQLModel, table=True):
    """Single extraction run for a given report."""

    __tablename__ = "extractions"

    id: str = Field(primary_key=True)
    report_id: str = Field(foreign_key="reports.id", index=True)
    created_at: str = Field(index=True)
    model_name: str
    reasoning_effort: str | None = None
    exam_description_hint: str | None = None
    study_description: str | None = None
    study_date: str | None = None
    modality: str | None = None
    body_part: str | None = None
    extraction_json: str
    validation_json: str | None = None


class CorrectionRow(SQLModel, table=True):
    """Human correction suggestions/comments for an extraction."""

    __tablename__ = "corrections"
    __table_args__ = (
        CheckConstraint(
            "correction_type IN ('add_finding', 'update_finding', 'comment')",
            name="check_correction_type",
        ),
        CheckConstraint(
            "status IN ('pending', 'accepted', 'rejected', 'applied')",
            name="check_correction_status",
        ),
    )

    id: str = Field(primary_key=True)
    extraction_id: str = Field(foreign_key="extractions.id", index=True)
    target_finding_index: int | None = None
    target_json_path: str | None = None
    correction_type: str
    status: str
    proposed_finding_json: str | None = None
    attribute_overrides_json: str | None = None
    comment: str | None = None
    created_by: str | None = None
    created_at: str


class JobRow(SQLModel, table=True):
    """Extraction job status row for async API polling."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed')",
            name="check_job_status",
        ),
    )

    id: str = Field(primary_key=True)
    report_id: str = Field(foreign_key="reports.id", index=True)
    status: str = Field(index=True)
    created_at: str = Field(index=True)
    started_at: str | None = None
    completed_at: str | None = None
    extraction_id: str | None = Field(default=None, foreign_key="extractions.id")
    error: str | None = None


@dataclass(frozen=True)
class StoredReport:
    """A persisted source report."""

    id: str
    text_hash: str
    source_ref: str | None
    created_at: str
    seen_before: bool = False


@dataclass(frozen=True)
class StoredReportDetail:
    """A persisted source report with body text."""

    id: str
    text_hash: str
    report_text: str
    source_ref: str | None
    created_at: str


@dataclass(frozen=True)
class StoredExtraction:
    """A persisted extraction run."""

    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None
    created_at: str


@dataclass(frozen=True)
class StoredExtractionDetail:
    """A persisted extraction with full deserialized payload."""

    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None
    exam_description_hint: str | None
    created_at: str
    extraction: ReportExtraction
    validation_result: ValidationResult | None


@dataclass(frozen=True)
class StoredCorrection:
    """A persisted user correction against an extraction."""

    id: str
    extraction_id: str
    target_finding_index: int | None
    target_json_path: str | None
    correction_type: CorrectionType
    status: CorrectionStatus
    comment: str | None
    created_by: str | None
    created_at: str


@dataclass(frozen=True)
class StoredJob:
    """A persisted background job for extraction execution."""

    id: str
    report_id: str
    status: JobStatus
    created_at: str
    started_at: str | None
    completed_at: str | None
    extraction_id: str | None
    error: str | None


def _utc_now_iso() -> str:
    """Return UTC timestamp in ISO-8601 format."""
    return datetime.now(UTC).isoformat()


def _hash_report_text(report_text: str) -> str:
    """Stable hash for report de-duplication."""
    return hashlib.sha256(report_text.encode("utf-8")).hexdigest()


class ExtractionStore:
    """Async SQLModel-backed persistence for reports, extraction runs, and corrections."""

    def __init__(self, db_path: Path | str):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine: AsyncEngine = create_async_engine(
            f"sqlite+aiosqlite:///{self._db_path}",
            echo=False,
        )
        self._configure_sqlite_pragmas()
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._initialized = False

    def _configure_sqlite_pragmas(self) -> None:
        """Apply SQLite pragmas that make API + worker access reliable."""

        @event.listens_for(self._engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
            _ = connection_record
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    @property
    def db_path(self) -> Path:
        """Configured SQLite path."""
        return self._db_path

    @property
    def engine(self) -> AsyncEngine:
        """Expose async engine for tests/integration wiring."""
        return self._engine

    async def init(self) -> None:
        """Initialize database tables (idempotent)."""
        if self._initialized:
            return
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        self._initialized = True

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide an AsyncSession context manager."""
        await self.init()
        async with self._session_factory() as session:
            yield session

    async def close(self) -> None:
        """Dispose async engine and pooled connections."""
        await self._engine.dispose()

    async def upsert_report(self, report_text: str, source_ref: str | None = None) -> StoredReport:
        """Insert report if unseen, otherwise return existing record."""
        text_hash = _hash_report_text(report_text)

        async with self.session() as session:
            existing = (
                await session.exec(select(ReportRow).where(ReportRow.text_hash == text_hash))
            ).first()
            if existing is not None:
                if source_ref and not existing.source_ref:
                    existing.source_ref = source_ref
                    session.add(existing)
                    await session.commit()
                    await session.refresh(existing)
                return StoredReport(
                    id=existing.id,
                    text_hash=existing.text_hash,
                    source_ref=existing.source_ref,
                    created_at=existing.created_at,
                    seen_before=True,
                )

            report = ReportRow(
                id=str(uuid4()),
                text_hash=text_hash,
                report_text=report_text,
                source_ref=source_ref,
                created_at=_utc_now_iso(),
            )
            session.add(report)
            await session.commit()

            return StoredReport(
                id=report.id,
                text_hash=report.text_hash,
                source_ref=report.source_ref,
                created_at=report.created_at,
                seen_before=False,
            )

    async def create_extraction(
        self,
        report_id: str,
        extraction: ReportExtraction,
        model_name: str,
        reasoning_effort: str | None = None,
        exam_description_hint: str | None = None,
        validation_result: ValidationResult | None = None,
    ) -> StoredExtraction:
        """Persist one extraction run payload."""
        created_at = _utc_now_iso()
        extraction_id = str(uuid4())
        extraction_json = json.dumps(extraction.model_dump(mode="json"), ensure_ascii=False)
        validation_json = (
            json.dumps(validation_result.model_dump(mode="json"), ensure_ascii=False)
            if validation_result is not None
            else None
        )

        async with self.session() as session:
            session.add(
                ExtractionRow(
                    id=extraction_id,
                    report_id=report_id,
                    created_at=created_at,
                    model_name=model_name,
                    reasoning_effort=reasoning_effort,
                    exam_description_hint=exam_description_hint,
                    study_description=extraction.exam_info.study_description,
                    study_date=(
                        extraction.exam_info.study_date.isoformat()
                        if extraction.exam_info.study_date is not None
                        else None
                    ),
                    modality=extraction.exam_info.modality,
                    body_part=extraction.exam_info.body_part,
                    extraction_json=extraction_json,
                    validation_json=validation_json,
                )
            )
            await session.commit()

        return StoredExtraction(
            id=extraction_id,
            report_id=report_id,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            created_at=created_at,
        )

    async def get_report(self, report_id: str) -> StoredReportDetail | None:
        """Fetch one report including report text."""
        async with self.session() as session:
            row = (await session.exec(select(ReportRow).where(ReportRow.id == report_id))).first()
        if row is None:
            return None
        return StoredReportDetail(
            id=row.id,
            text_hash=row.text_hash,
            report_text=row.report_text,
            source_ref=row.source_ref,
            created_at=row.created_at,
        )

    async def list_reports(self, limit: int = 50, offset: int = 0) -> list[StoredReport]:
        """List reports (without report text) with pagination."""
        async with self.session() as session:
            rows = (
                await session.exec(
                    select(ReportRow)
                    .order_by(col(ReportRow.created_at).desc(), col(ReportRow.id).desc())
                    .limit(limit)
                    .offset(offset)
                )
            ).all()
        return [
            StoredReport(
                id=row.id,
                text_hash=row.text_hash,
                source_ref=row.source_ref,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def get_extraction(self, extraction_id: str) -> StoredExtractionDetail | None:
        """Fetch one extraction with deserialized JSON payloads."""
        async with self.session() as session:
            row = (
                await session.exec(select(ExtractionRow).where(ExtractionRow.id == extraction_id))
            ).first()
        if row is None:
            return None

        extraction_payload = ReportExtraction.model_validate(json.loads(row.extraction_json))
        validation_payload = (
            ValidationResult.model_validate(json.loads(row.validation_json))
            if row.validation_json is not None
            else None
        )
        return StoredExtractionDetail(
            id=row.id,
            report_id=row.report_id,
            model_name=row.model_name,
            reasoning_effort=row.reasoning_effort,
            exam_description_hint=row.exam_description_hint,
            created_at=row.created_at,
            extraction=extraction_payload,
            validation_result=validation_payload,
        )

    async def list_extractions(self, report_id: str) -> list[StoredExtraction]:
        """List extraction summaries for a report."""
        async with self.session() as session:
            rows = (
                await session.exec(
                    select(ExtractionRow)
                    .where(ExtractionRow.report_id == report_id)
                    .order_by(col(ExtractionRow.created_at).desc(), col(ExtractionRow.id).desc())
                )
            ).all()
        return [
            StoredExtraction(
                id=row.id,
                report_id=row.report_id,
                model_name=row.model_name,
                reasoning_effort=row.reasoning_effort,
                created_at=row.created_at,
            )
            for row in rows
        ]

    async def create_job(self, job_id: str, report_id: str, status: JobStatus = "pending") -> StoredJob:
        """Create a job row before enqueueing worker execution."""
        job = JobRow(
            id=job_id,
            report_id=report_id,
            status=status,
            created_at=_utc_now_iso(),
        )
        async with self.session() as session:
            session.add(job)
            await session.commit()
        return StoredJob(
            id=job.id,
            report_id=job.report_id,
            status=job.status,  # type: ignore[arg-type]
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            extraction_id=job.extraction_id,
            error=job.error,
        )

    async def get_job(self, job_id: str) -> StoredJob | None:
        """Fetch a persisted job by id."""
        async with self.session() as session:
            row = (await session.exec(select(JobRow).where(JobRow.id == job_id))).first()
        if row is None:
            return None
        return StoredJob(
            id=row.id,
            report_id=row.report_id,
            status=row.status,  # type: ignore[arg-type]
            created_at=row.created_at,
            started_at=row.started_at,
            completed_at=row.completed_at,
            extraction_id=row.extraction_id,
            error=row.error,
        )

    async def mark_job_running(self, job_id: str) -> None:
        """Transition an existing job to running."""
        async with self.session() as session:
            row = (await session.exec(select(JobRow).where(JobRow.id == job_id))).first()
            if row is None:
                raise ValueError(f"Unknown job_id: {job_id}")
            row.status = "running"
            row.started_at = _utc_now_iso()
            row.error = None
            session.add(row)
            await session.commit()

    async def mark_job_completed(self, job_id: str, extraction_id: str) -> None:
        """Transition an existing job to completed with extraction id."""
        async with self.session() as session:
            row = (await session.exec(select(JobRow).where(JobRow.id == job_id))).first()
            if row is None:
                raise ValueError(f"Unknown job_id: {job_id}")
            row.status = "completed"
            row.completed_at = _utc_now_iso()
            row.extraction_id = extraction_id
            row.error = None
            session.add(row)
            await session.commit()

    async def mark_job_failed(self, job_id: str, error: str) -> None:
        """Transition an existing job to failed with error details."""
        async with self.session() as session:
            row = (await session.exec(select(JobRow).where(JobRow.id == job_id))).first()
            if row is None:
                raise ValueError(f"Unknown job_id: {job_id}")
            row.status = "failed"
            row.completed_at = _utc_now_iso()
            row.error = error
            session.add(row)
            await session.commit()

    async def get_finding_path(self, extraction_id: str, finding_index: int) -> str | None:
        """Return JSON path for a finding index if it exists in extraction payload."""
        async with self.session() as session:
            row = (await session.exec(select(ExtractionRow).where(ExtractionRow.id == extraction_id))).first()
            if row is None:
                return None
            payload = json.loads(row.extraction_json)

        findings = payload.get("findings", [])
        if not isinstance(findings, list):
            return None
        if finding_index < 0 or finding_index >= len(findings):
            return None
        return f"$.findings[{finding_index}]"

    async def record_correction(
        self,
        extraction_id: str,
        correction_type: CorrectionType,
        *,
        target_finding_index: int | None = None,
        target_json_path: str | None = None,
        proposed_finding: ExtractedFinding | None = None,
        attribute_overrides: dict[str, str] | None = None,
        comment: str | None = None,
        created_by: str | None = None,
        status: CorrectionStatus = "pending",
    ) -> StoredCorrection:
        """Store user correction suggestions for later review/apply steps."""
        if correction_type == "add_finding" and proposed_finding is None:
            raise ValueError("add_finding corrections require proposed_finding")
        if correction_type == "update_finding" and (
            target_finding_index is None and target_json_path is None
        ):
            raise ValueError("update_finding corrections require target_finding_index or target_json_path")
        if correction_type == "comment" and not comment:
            raise ValueError("comment corrections require comment text")

        if target_json_path is None and target_finding_index is not None:
            target_json_path = await self.get_finding_path(extraction_id, target_finding_index)
            if correction_type == "update_finding" and target_json_path is None:
                raise ValueError("update_finding target_finding_index does not exist in extraction findings")

        correction_id = str(uuid4())
        created_at = _utc_now_iso()
        proposed_finding_json = (
            json.dumps(proposed_finding.model_dump(mode="json"), ensure_ascii=False)
            if proposed_finding is not None
            else None
        )
        attribute_overrides_json = (
            json.dumps(attribute_overrides, ensure_ascii=False) if attribute_overrides else None
        )

        async with self.session() as session:
            session.add(
                CorrectionRow(
                    id=correction_id,
                    extraction_id=extraction_id,
                    target_finding_index=target_finding_index,
                    target_json_path=target_json_path,
                    correction_type=correction_type,
                    status=status,
                    proposed_finding_json=proposed_finding_json,
                    attribute_overrides_json=attribute_overrides_json,
                    comment=comment,
                    created_by=created_by,
                    created_at=created_at,
                )
            )
            await session.commit()

        return StoredCorrection(
            id=correction_id,
            extraction_id=extraction_id,
            target_finding_index=target_finding_index,
            target_json_path=target_json_path,
            correction_type=correction_type,
            status=status,
            comment=comment,
            created_by=created_by,
            created_at=created_at,
        )

    async def list_corrections(self, extraction_id: str) -> list[StoredCorrection]:
        """List correction records for a given extraction."""
        async with self.session() as session:
            rows = (
                await session.exec(
                    select(CorrectionRow)
                    .where(CorrectionRow.extraction_id == extraction_id)
                    .order_by(CorrectionRow.created_at, CorrectionRow.id)
                )
            ).all()

        return [
            StoredCorrection(
                id=row.id,
                extraction_id=row.extraction_id,
                target_finding_index=row.target_finding_index,
                target_json_path=row.target_json_path,
                correction_type=row.correction_type,  # type: ignore[arg-type]
                status=row.status,  # type: ignore[arg-type]
                comment=row.comment,
                created_by=row.created_by,
                created_at=row.created_at,
            )
            for row in rows
        ]
