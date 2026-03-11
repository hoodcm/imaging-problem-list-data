"""Service helpers for API endpoint orchestration."""

from typing import Any
from uuid import uuid4

import structlog
from fastapi import HTTPException

from finding_extractor.api.schemas import TriggerExtractionRequest
from finding_extractor.core.config import get_settings
from finding_extractor.db.store import ExtractionStore, StoredExtractionDetail, StoredReportDetail
from finding_extractor.llm.model_settings import resolve_runtime_reasoning
from finding_extractor.llm.policy import validate_model_id

logger = structlog.get_logger(__name__)


async def require_report(store: ExtractionStore, report_id: str) -> StoredReportDetail:
    """Load report or raise 404."""
    report = await store.get_report(report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


async def require_extraction(store: ExtractionStore, extraction_id: str) -> StoredExtractionDetail:
    """Load extraction or raise 404."""
    extraction = await store.get_extraction(extraction_id)
    if extraction is None:
        raise HTTPException(status_code=404, detail="Extraction not found")
    return extraction


async def enqueue_extraction_job(
    *,
    store: ExtractionStore,
    run_extraction_task: Any,
    report_id: str,
    body: TriggerExtractionRequest,
) -> str:
    """Create a pending job and enqueue worker execution."""
    logger.info("Extraction enqueue requested", report_id=report_id)
    await require_report(store, report_id)
    settings = get_settings()
    model_name = body.model or settings.default_model
    try:
        validate_model_id(model_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        effective_reasoning = resolve_runtime_reasoning(
            model_name,
            body.reasoning,
            allow_unknown_model_reasoning=settings.allow_unknown_model_reasoning,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = str(uuid4())
    await store.create_job(job_id=job_id, report_id=report_id, status="pending")
    logger.info(
        "Pending extraction job created",
        job_id=job_id,
        report_id=report_id,
        model_name=model_name,
        reliability_mode=body.reliability_mode,
        validate_output=body.validate_output,
    )

    try:
        await run_extraction_task.kiq(
            job_id,
            report_id,
            model_name,
            effective_reasoning,
            body.study_description,
            body.reliability_mode,
            body.validate_output,
        )
    except Exception as exc:
        logger.exception(
            "Extraction job enqueue failed",
            job_id=job_id,
            report_id=report_id,
        )
        await store.mark_job_failed(job_id, error="enqueue_failed:queue_unavailable")
        raise HTTPException(status_code=503, detail="Failed to enqueue extraction job") from exc

    logger.info("Extraction job enqueued", job_id=job_id, report_id=report_id)
    return job_id
