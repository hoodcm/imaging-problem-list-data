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
)
from finding_extractor.broker import broker
from finding_extractor.config import get_settings
from finding_extractor.extraction_orchestrator import (
    format_stage_status,
    run_orchestrated_extraction,
)
from finding_extractor.model_policy import validate_model_id
from finding_extractor.models import (
    JobWarningPayload,
    ReliabilityMode,
    ReportExtraction,
    WarningReasonCategory,
)
from finding_extractor.providers import resolve_effective_reasoning
from finding_extractor.store import ExtractionStore

logger = structlog.get_logger(__name__)


class ReliabilityContractError(Exception):
    """Raised when strict reliability mode must terminate a job as failed."""

    def __init__(self, public_error: str, warning_payload: JobWarningPayload) -> None:
        super().__init__(public_error)
        self.public_error = public_error
        self.warning_payload = warning_payload


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


def _is_verbatim_match(report_text: str, span: str) -> bool:
    snippet = span.strip()
    if not snippet:
        return False
    return snippet in report_text


def _drop_non_verbatim_segments(
    report_text: str, extraction: ReportExtraction
) -> tuple[ReportExtraction, int, int]:
    kept_findings = [f for f in extraction.findings if _is_verbatim_match(report_text, f.report_text)]
    kept_non_finding = [s for s in extraction.non_finding_text if _is_verbatim_match(report_text, s.text)]
    dropped_findings_count = len(extraction.findings) - len(kept_findings)
    dropped_non_finding_count = len(extraction.non_finding_text) - len(kept_non_finding)
    normalized = extraction.model_copy(
        update={"findings": kept_findings, "non_finding_text": kept_non_finding}
    )
    return normalized, dropped_findings_count, dropped_non_finding_count


def _build_warning_payload(
    *,
    reliability_mode: ReliabilityMode,
    dropped_findings_count: int,
    dropped_non_finding_count: int,
    validation_error_count: int,
    coverage_warning_count: int,
) -> JobWarningPayload | None:
    reason_categories: list[WarningReasonCategory] = []
    if validation_error_count > 0:
        reason_categories.append("validation_failed")
    if dropped_findings_count > 0 or dropped_non_finding_count > 0:
        reason_categories.append("verbatim_mismatch")
    has_primary_warning = validation_error_count > 0 or (
        dropped_findings_count > 0 or dropped_non_finding_count > 0
    )
    if coverage_warning_count > 0 and has_primary_warning:
        reason_categories.append("coverage_gap")

    if not reason_categories:
        return None

    ordered_categories: list[WarningReasonCategory] = []
    for category in ("validation_failed", "verbatim_mismatch", "coverage_gap"):
        if category in reason_categories:
            ordered_categories.append(category)

    return JobWarningPayload(
        reliability_mode=reliability_mode,
        reason_categories=ordered_categories,
        dropped_findings_count=dropped_findings_count,
        dropped_non_finding_count=dropped_non_finding_count,
        validation_error_count=validation_error_count,
        coverage_warning_count=coverage_warning_count,
    )


async def _run_extraction_impl(
    job_id: str,
    report_id: str,
    store: ExtractionStore,
    model: str | None = None,
    reasoning: str | None = None,
    exam_description: str | None = None,
    reliability_mode: ReliabilityMode = "strict",
    validate: bool = True,
) -> dict[str, str]:
    """Core extraction logic shared by default and test brokers."""
    clear_contextvars()
    bind_contextvars(job_id=job_id, report_id=report_id)
    try:
        logger.info("Extraction task started", model=model, validate=validate)
        await store.mark_job_running(job_id)

        await store.update_job_status_message(
            job_id,
            format_stage_status("preflight", "retrieving_report"),
        )
        report = await store.get_report(report_id)
        if report is None:
            raise ValueError(f"Unknown report_id: {report_id}")

        await store.update_job_status_message(
            job_id,
            format_stage_status("preflight", "validating_model_configuration"),
        )
        model_name = model or get_settings().default_model
        validate_model_id(model_name)
        resolve_effective_reasoning(model_name, reasoning)
        logger.info("Extraction model configuration validated", model_name=model_name)

        async def _status_cb(message: str) -> None:
            logger.debug("Extraction task status update", status_message=message)
            await store.update_job_status_message(job_id, message)

        settings = get_settings()

        async def _apply_coding(extraction):
            from finding_extractor.coding_bridge import apply_coding

            return await apply_coding(extraction)

        orchestrated = await run_orchestrated_extraction(
            report_text=report.report_text,
            exam_description=exam_description,
            model_name=model_name,
            reasoning=reasoning,
            validate=validate,
            coding_enabled=settings.coding_enabled,
            emit_status=_status_cb,
            extract_findings_fn=extract_findings,
            validate_extraction_fn=validate_extraction,
            apply_coding_fn=_apply_coding if settings.coding_enabled else None,
            modular_pipeline_enabled=getattr(settings, "modular_pipeline_enabled", False),
            section_max_concurrency=getattr(settings, "modular_pipeline_max_concurrency", 2),
            section_repair_attempts=getattr(settings, "modular_pipeline_repair_attempts", 1),
            logger=logger,
        )
        extraction = orchestrated.extraction
        usage = orchestrated.usage
        logger.info(
            "Extraction model call complete",
            model_name=model_name,
            findings_count=len(extraction.findings),
            non_finding_count=len(extraction.non_finding_text),
        )
        validation_result = orchestrated.validation_result
        coding_result = orchestrated.coding_result
        dropped_findings_count = 0
        dropped_non_finding_count = 0
        validation_error_count = 0
        coverage_warning_count = 0
        if validate and validation_result is not None:
            validation_error_count = len(validation_result.verbatim_errors)
            if not validation_result.is_valid:
                validation_error_count = max(validation_error_count, 1)
            coverage_warning_count = len(validation_result.coverage_warnings)
            extraction, dropped_findings_count, dropped_non_finding_count = _drop_non_verbatim_segments(
                report.report_text,
                extraction,
            )
        warning_payload = _build_warning_payload(
            reliability_mode=reliability_mode,
            dropped_findings_count=dropped_findings_count,
            dropped_non_finding_count=dropped_non_finding_count,
            validation_error_count=validation_error_count,
            coverage_warning_count=coverage_warning_count,
        )
        if (
            reliability_mode == "strict"
            and warning_payload is not None
            and validation_error_count > 0
        ):
            raise ReliabilityContractError(
                "extraction_failed:validation_failed",
                warning_payload,
            )

        await store.update_job_status_message(
            job_id,
            format_stage_status("persist", "saving_extraction_results"),
        )
        extraction_record = await store.create_extraction(
            report_id=report_id,
            extraction=extraction,
            model_name=model_name,
            reasoning_effort=reasoning,
            exam_description_hint=exam_description,
            validation_result=validation_result,
            usage=usage,
            coding_result=coding_result,
        )
        await store.update_job_status_message(
            job_id,
            format_stage_status("completed", "extraction_complete"),
        )
        if warning_payload is None:
            await store.mark_job_completed(job_id, extraction_id=extraction_record.id)
        else:
            await store.mark_job_completed_with_warnings(
                job_id,
                extraction_id=extraction_record.id,
                warning_payload=warning_payload,
            )
        logger.info(
            "Extraction task completed",
            extraction_id=extraction_record.id,
            model_name=model_name,
            warning_payload=(
                warning_payload.model_dump(mode="json") if warning_payload is not None else None
            ),
        )
        return {
            "extraction_id": extraction_record.id,
            "model_name": model_name,
        }
    except Exception as exc:
        warning_payload = None
        if isinstance(exc, ReliabilityContractError):
            public_error = exc.public_error
            warning_payload = exc.warning_payload
        else:
            public_error = to_public_job_error(exc)
        logger.exception("Extraction task failed", public_error=public_error)
        with suppress(ValueError):
            await store.update_job_status_message(
                job_id,
                format_stage_status("failed", public_error),
            )
            await store.mark_job_failed(
                job_id,
                error=public_error,
                warning_payload=warning_payload,
            )
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
        reliability_mode: ReliabilityMode = "strict",
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
            reliability_mode=reliability_mode,
            validate=validate,
        )

    return _run_extraction_task


run_extraction = register_run_extraction_task(broker)
