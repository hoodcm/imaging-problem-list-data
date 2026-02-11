"""TaskIQ tasks for background extraction processing."""

import logging
from contextlib import suppress
from typing import Annotated

from fastapi import Request
from taskiq import TaskiqDepends

from finding_extractor.agent import (
    extract_findings,
    validate_extraction,
    validate_reasoning_for_model,
)
from finding_extractor.broker import broker
from finding_extractor.config import get_settings
from finding_extractor.model_policy import validate_model_id
from finding_extractor.observability import configure_logfire
from finding_extractor.store import ExtractionStore

logger = logging.getLogger(__name__)


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
    configure_logfire(runtime="worker")
    try:
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

        async def _status_cb(message: str) -> None:
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

        if validate:
            await store.update_job_status_message(job_id, "Validating extraction results")
        validation_result = validate_extraction(report.report_text, extraction) if validate else None

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
        return {
            "extraction_id": extraction_record.id,
            "model_name": model_name,
        }
    except Exception as exc:
        logger.exception("Extraction task failed for job_id=%s report_id=%s", job_id, report_id)
        with suppress(ValueError):
            await store.mark_job_failed(job_id, error=to_public_job_error(exc))
        raise


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
