"""FastAPI server exposing report/extraction persistence and async jobs."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field

from finding_extractor.models import ExtractedFinding, ReportExtraction, ValidationResult
from finding_extractor.store import (
    CorrectionStatus,
    CorrectionType,
    ExtractionStore,
)
from finding_extractor.tasks import register_run_extraction_task, run_extraction

JobStatus = Literal["pending", "running", "completed", "failed"]
logger = logging.getLogger(__name__)


async def assert_broker_ready(broker: Any) -> None:
    """Check broker backend connectivity for extraction dispatch readiness.

    Redis-backed brokers expose ``connection_pool``. Non-Redis test brokers
    (for example TaskIQ InMemoryBroker) are treated as locally ready.
    """

    connection_pool = getattr(broker, "connection_pool", None)
    if connection_pool is None:
        return

    from redis.asyncio import Redis

    async with Redis(connection_pool=connection_pool) as redis_conn:
        ping_result = redis_conn.ping()
        ping_ok = await ping_result if hasattr(ping_result, "__await__") else ping_result
        if ping_ok is not True:
            raise RuntimeError("Broker backend ping failed")


class SubmitReportRequest(BaseModel):
    """Payload for report create/upsert."""

    model_config = ConfigDict(extra="forbid")

    report_text: str = Field(min_length=1)
    source_ref: str | None = None


class ReportResponse(BaseModel):
    """Summary response for report rows."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text_hash: str
    source_ref: str | None = None
    created_at: str
    seen_before: bool = False


class ReportDetailResponse(BaseModel):
    """Detailed report payload including text."""

    model_config = ConfigDict(extra="forbid")

    id: str
    text_hash: str
    report_text: str
    source_ref: str | None = None
    created_at: str


class TriggerExtractionRequest(BaseModel):
    """Payload for queueing extraction."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    model: str | None = None
    reasoning: str | None = None
    exam_description: str | None = None
    validate_output: bool = Field(default=True, alias="validate")


class TriggerExtractionResponse(BaseModel):
    """Accepted job response for async extraction."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    report_id: str
    status: JobStatus


class JobResponse(BaseModel):
    """Job polling response."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    report_id: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    extraction_id: str | None = None
    error: str | None = None


class ExtractionSummaryResponse(BaseModel):
    """Extraction list row."""

    model_config = ConfigDict(extra="forbid")

    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None = None
    created_at: str


class ExtractionDetailResponse(BaseModel):
    """Extraction detail payload."""

    model_config = ConfigDict(extra="forbid")

    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None = None
    exam_description_hint: str | None = None
    created_at: str
    extraction: ReportExtraction
    validation_result: ValidationResult | None = None


class CreateCorrectionRequest(BaseModel):
    """Payload for correction creation."""

    model_config = ConfigDict(extra="forbid")

    correction_type: CorrectionType
    target_finding_index: int | None = None
    target_json_path: str | None = None
    proposed_finding: ExtractedFinding | None = None
    attribute_overrides: dict[str, str] | None = None
    comment: str | None = None
    created_by: str | None = None
    status: CorrectionStatus = "pending"


class CorrectionResponse(BaseModel):
    """Correction list/create response."""

    model_config = ConfigDict(extra="forbid")

    id: str
    extraction_id: str
    target_finding_index: int | None = None
    target_json_path: str | None = None
    correction_type: CorrectionType
    status: CorrectionStatus
    comment: str | None = None
    created_by: str | None = None
    created_at: str


class HealthResponse(BaseModel):
    """Basic health/readiness response."""

    model_config = ConfigDict(extra="forbid")

    status: str


def _resolve_db_path() -> Path:
    db_path = os.getenv("FINDING_EXTRACTOR_DB_PATH")
    if db_path:
        return Path(db_path)
    return Path(".finding_extractor.db")


def _resolve_cors_origins() -> list[str]:
    raw = os.getenv("FINDING_EXTRACTOR_CORS_ORIGINS")
    if not raw:
        return ["http://localhost:8000", "http://127.0.0.1:8000"]
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or ["*"]


def get_store(request: Request) -> ExtractionStore:
    """HTTP dependency for persistence access."""
    return request.app.state.store


def create_app(store: ExtractionStore | None = None, broker: Any = None) -> FastAPI:
    """Create FastAPI app with injectable store/broker for tests."""
    uses_custom_broker = broker is not None
    if broker is None:
        from finding_extractor.broker import broker as default_broker

        broker = default_broker

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store or ExtractionStore(_resolve_db_path())
        app.state.broker = broker
        app.state.run_extraction_task = (
            register_run_extraction_task(app.state.broker) if uses_custom_broker else run_extraction
        )
        await app.state.store.init()
        if not app.state.broker.is_worker_process:
            await app.state.broker.startup()
        try:
            yield
        finally:
            if not app.state.broker.is_worker_process:
                await app.state.broker.shutdown()
            await app.state.store.close()

    app = FastAPI(title="Finding Extractor API", version="0.1.0", lifespan=lifespan)
    cors_origins = _resolve_cors_origins()
    app.add_middleware(
        CORSMiddleware,  # ty: ignore[invalid-argument-type]
        allow_origins=cors_origins,
        allow_credentials=cors_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        """Liveness probe for process-level health."""
        return HealthResponse(status="ok")

    @app.get("/api/readyz", response_model=HealthResponse)
    async def readyz(
        *,
        store: Annotated[ExtractionStore, Depends(get_store)],
        request: Request,
    ) -> HealthResponse:
        """Readiness probe for API/database and queue backend availability."""
        try:
            await store.list_reports(limit=1, offset=0)
            await assert_broker_ready(request.app.state.broker)
        except Exception as exc:
            logger.exception("Readiness check failed")
            raise HTTPException(status_code=503, detail="Not ready") from exc
        return HealthResponse(status="ready")

    @app.post("/api/reports", response_model=ReportResponse)
    async def submit_report(
        body: SubmitReportRequest,
        store: Annotated[ExtractionStore, Depends(get_store)],
    ) -> ReportResponse:
        report = await store.upsert_report(body.report_text, source_ref=body.source_ref)
        return ReportResponse(
            id=report.id,
            text_hash=report.text_hash,
            source_ref=report.source_ref,
            created_at=report.created_at,
            seen_before=report.seen_before,
        )

    @app.get("/api/reports", response_model=list[ReportResponse])
    async def list_reports(
        limit: int = Query(default=50, ge=1, le=200),
        offset: int = Query(default=0, ge=0),
        *,
        store: Annotated[ExtractionStore, Depends(get_store)],
    ) -> list[ReportResponse]:
        reports = await store.list_reports(limit=limit, offset=offset)
        return [
            ReportResponse(
                id=report.id,
                text_hash=report.text_hash,
                source_ref=report.source_ref,
                created_at=report.created_at,
                seen_before=report.seen_before,
            )
            for report in reports
        ]

    @app.get("/api/reports/{report_id}", response_model=ReportDetailResponse)
    async def get_report(
        report_id: str,
        *,
        store: Annotated[ExtractionStore, Depends(get_store)],
    ) -> ReportDetailResponse:
        report = await store.get_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        return ReportDetailResponse(
            id=report.id,
            text_hash=report.text_hash,
            report_text=report.report_text,
            source_ref=report.source_ref,
            created_at=report.created_at,
        )

    @app.post(
        "/api/reports/{report_id}/extract",
        status_code=202,
        response_model=TriggerExtractionResponse,
    )
    async def trigger_extraction(
        report_id: str,
        body: TriggerExtractionRequest,
        request: Request,
        response: Response,
        *,
        store: Annotated[ExtractionStore, Depends(get_store)],
    ) -> TriggerExtractionResponse:
        report = await store.get_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")

        job_id = str(uuid4())
        await store.create_job(job_id=job_id, report_id=report_id, status="pending")

        try:
            await request.app.state.run_extraction_task.kiq(
                job_id,
                report_id,
                body.model,
                body.reasoning,
                body.exam_description,
                body.validate_output,
            )
        except Exception as exc:
            logger.exception("Failed to enqueue extraction job for job_id=%s report_id=%s", job_id, report_id)
            await store.mark_job_failed(job_id, error="enqueue_failed:queue_unavailable")
            raise HTTPException(status_code=503, detail="Failed to enqueue extraction job") from exc

        response.headers["Location"] = f"/api/jobs/{job_id}"
        response.headers["Retry-After"] = "2"
        return TriggerExtractionResponse(job_id=job_id, report_id=report_id, status="pending")

    @app.get("/api/jobs/{job_id}", response_model=JobResponse)
    async def get_job_status(
        job_id: str,
        *,
        store: Annotated[ExtractionStore, Depends(get_store)],
    ) -> JobResponse:
        job = await store.get_job(job_id)
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")
        return JobResponse(
            job_id=job.id,
            report_id=job.report_id,
            status=job.status,
            created_at=job.created_at,
            started_at=job.started_at,
            completed_at=job.completed_at,
            extraction_id=job.extraction_id,
            error=job.error,
        )

    @app.get("/api/reports/{report_id}/extractions", response_model=list[ExtractionSummaryResponse])
    async def list_report_extractions(
        report_id: str,
        *,
        store: Annotated[ExtractionStore, Depends(get_store)],
    ) -> list[ExtractionSummaryResponse]:
        report = await store.get_report(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="Report not found")
        extractions = await store.list_extractions(report_id)
        return [
            ExtractionSummaryResponse(
                id=extraction.id,
                report_id=extraction.report_id,
                model_name=extraction.model_name,
                reasoning_effort=extraction.reasoning_effort,
                created_at=extraction.created_at,
            )
            for extraction in extractions
        ]

    @app.get("/api/extractions/{extraction_id}", response_model=ExtractionDetailResponse)
    async def get_extraction(
        extraction_id: str,
        *,
        store: Annotated[ExtractionStore, Depends(get_store)],
    ) -> ExtractionDetailResponse:
        extraction = await store.get_extraction(extraction_id)
        if extraction is None:
            raise HTTPException(status_code=404, detail="Extraction not found")
        return ExtractionDetailResponse(
            id=extraction.id,
            report_id=extraction.report_id,
            model_name=extraction.model_name,
            reasoning_effort=extraction.reasoning_effort,
            exam_description_hint=extraction.exam_description_hint,
            created_at=extraction.created_at,
            extraction=extraction.extraction,
            validation_result=extraction.validation_result,
        )

    @app.post(
        "/api/extractions/{extraction_id}/corrections",
        status_code=201,
        response_model=CorrectionResponse,
    )
    async def create_correction(
        extraction_id: str,
        body: CreateCorrectionRequest,
        *,
        store: Annotated[ExtractionStore, Depends(get_store)],
    ) -> CorrectionResponse:
        extraction = await store.get_extraction(extraction_id)
        if extraction is None:
            raise HTTPException(status_code=404, detail="Extraction not found")
        try:
            correction = await store.record_correction(
                extraction_id=extraction_id,
                correction_type=body.correction_type,
                target_finding_index=body.target_finding_index,
                target_json_path=body.target_json_path,
                proposed_finding=body.proposed_finding,
                attribute_overrides=body.attribute_overrides,
                comment=body.comment,
                created_by=body.created_by,
                status=body.status,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        return CorrectionResponse(
            id=correction.id,
            extraction_id=correction.extraction_id,
            target_finding_index=correction.target_finding_index,
            target_json_path=correction.target_json_path,
            correction_type=correction.correction_type,
            status=correction.status,
            comment=correction.comment,
            created_by=correction.created_by,
            created_at=correction.created_at,
        )

    @app.get("/api/extractions/{extraction_id}/corrections", response_model=list[CorrectionResponse])
    async def list_extraction_corrections(
        extraction_id: str,
        *,
        store: Annotated[ExtractionStore, Depends(get_store)],
    ) -> list[CorrectionResponse]:
        extraction = await store.get_extraction(extraction_id)
        if extraction is None:
            raise HTTPException(status_code=404, detail="Extraction not found")
        corrections = await store.list_corrections(extraction_id)
        return [
            CorrectionResponse(
                id=correction.id,
                extraction_id=correction.extraction_id,
                target_finding_index=correction.target_finding_index,
                target_json_path=correction.target_json_path,
                correction_type=correction.correction_type,
                status=correction.status,
                comment=correction.comment,
                created_by=correction.created_by,
                created_at=correction.created_at,
            )
            for correction in corrections
        ]

    return app


app = create_app()


def main() -> None:
    """CLI entrypoint for running the API server."""
    uvicorn.run("finding_extractor.api:app", host="0.0.0.0", port=8001, reload=False)


if __name__ == "__main__":
    main()
