"""TaskIQ tasks for background extraction processing."""

from contextlib import suppress
from typing import Annotated

import structlog
from fastapi import Request
from structlog.contextvars import bind_contextvars, clear_contextvars
from taskiq import TaskiqDepends

from finding_extractor.agent import (
    extract_findings,
    validate_extraction,
    validate_reasoning_for_model,
)
from finding_extractor.broker import broker
from finding_extractor.config import get_settings
from finding_extractor.model_policy import validate_model_id
from finding_extractor.store import ExtractionStore

logger = structlog.get_logger(__name__)


def get_task_store(request: Annotated[Request, TaskiqDepends()]) -> ExtractionStore:
    """Task dependency that retrieves store from FastAPI app state."""
    return request.app.state.store


def to_public_job_error(exc: Exception) -> str:
    """Return a stable, non-sensitive job error string for API responses."""
    class_name = type(exc).__name__
    if isinstance(exc, ValueError):
        return "extraction_failed:invalid_request"
    if class_name == "ModelHTTPError":
        return "extraction_failed:model_provider_error"
    if class_name == "UnexpectedModelBehavior":
        return "extraction_failed:model_output_validation_failed"
    if class_name in {"TimeoutError", "APITimeoutError"}:
        return "extraction_failed:model_timeout"
    return "extraction_failed:internal_error"


async def _run_extraction_impl(
    job_id: str,
    report_id: str,
    store: ExtractionStore,
    model: str | None = None,
    reasoning: str | None = None,
    exam_description: str | None = None,
    validate: bool = True,
) -> dict[str, str]:
    """Core extraction logic shared by default and test brokers."""
    clear_contextvars()
    bind_contextvars(job_id=job_id, report_id=report_id)
    try:
        logger.info("Extraction task started", model=model, validate=validate)
        await store.mark_job_running(job_id)

        await store.update_job_status_message(job_id, "Retrieving report")
        report = await store.get_report(report_id)
        if report is None:
            raise ValueError(f"Unknown report_id: {report_id}")

        await store.update_job_status_message(job_id, "Validating model configuration")
        model_name = model or get_settings().default_model
        validate_model_id(model_name)
        if reasoning is not None:
            validate_reasoning_for_model(model_name, reasoning)
        logger.info("Extraction model configuration validated", model_name=model_name)

        async def _status_cb(message: str) -> None:
            logger.debug("Extraction task status update", status_message=message)
            await store.update_job_status_message(job_id, message)

        extraction_result = await extract_findings(
            report_text=report.report_text,
            exam_description=exam_description,
            model=model_name,
            reasoning=reasoning,
            status_callback=_status_cb,
        )
        extraction = extraction_result.extraction
        usage = extraction_result.usage
        logger.info(
            "Extraction model call complete",
            model_name=model_name,
            findings_count=len(extraction.findings),
            non_finding_count=len(extraction.non_finding_text),
        )

        if validate:
            await store.update_job_status_message(job_id, "Validating extraction results")
        validation_result = (
            validate_extraction(report.report_text, extraction) if validate else None
        )

        await store.update_job_status_message(job_id, "Saving extraction results")
        extraction_record = await store.create_extraction(
            report_id=report_id,
            extraction=extraction,
            model_name=model_name,
            reasoning_effort=reasoning,
            exam_description_hint=exam_description,
            validation_result=validation_result,
            usage=usage,
        )
        await store.mark_job_completed(job_id, extraction_id=extraction_record.id)
        logger.info(
            "Extraction task completed",
            extraction_id=extraction_record.id,
            model_name=model_name,
        )
        return {
            "extraction_id": extraction_record.id,
            "model_name": model_name,
        }
    except Exception as exc:
        public_error = to_public_job_error(exc)
        logger.exception("Extraction task failed", public_error=public_error)
        with suppress(ValueError):
            await store.mark_job_failed(job_id, error=public_error)
        raise
    finally:
        clear_contextvars()


def register_run_extraction_task(task_broker):
    """Bind the extraction task to a broker instance."""

    @task_broker.task(task_name="run_extraction")
    async def _run_extraction_task(
        job_id: str,
        report_id: str,
        model: str | None = None,
        reasoning: str | None = None,
        exam_description: str | None = None,
        validate: bool = True,
        *,
        store: Annotated[ExtractionStore, TaskiqDepends(get_task_store)],
    ) -> dict[str, str]:
        return await _run_extraction_impl(
            job_id=job_id,
            report_id=report_id,
            store=store,
            model=model,
            reasoning=reasoning,
            exam_description=exam_description,
            validate=validate,
        )

    return _run_extraction_task


run_extraction = register_run_extraction_task(broker)
