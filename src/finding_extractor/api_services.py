"""Service helpers for API endpoint orchestration."""

import logging
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from finding_extractor.api_models import TriggerExtractionRequest
from finding_extractor.config import get_settings
from finding_extractor.model_policy import validate_model_id
from finding_extractor.store import ExtractionStore, StoredExtractionDetail, StoredReportDetail

logger = logging.getLogger(__name__)


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
    await require_report(store, report_id)
    model_name = body.model or get_settings().default_model
    try:
        validate_model_id(model_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    job_id = str(uuid4())
    await store.create_job(job_id=job_id, report_id=report_id, status="pending")

    try:
        await run_extraction_task.kiq(
            job_id,
            report_id,
            model_name,
            body.reasoning,
            body.exam_description,
            body.validate_output,
        )
    except Exception as exc:
        logger.exception("Failed to enqueue extraction job for job_id=%s report_id=%s", job_id, report_id)
        await store.mark_job_failed(job_id, error="enqueue_failed:queue_unavailable")
        raise HTTPException(status_code=503, detail="Failed to enqueue extraction job") from exc

    return job_id
