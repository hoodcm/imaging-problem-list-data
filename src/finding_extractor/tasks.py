"""TaskIQ tasks for background extraction processing."""

from contextlib import suppress
from typing import Annotated

import structlog
from fastapi import Request
from pydantic_ai.exceptions import (
    FallbackExceptionGroup,
    ModelAPIError,
    UnexpectedModelBehavior,
)
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
from finding_extractor.extraction_review import review_extraction_units
from finding_extractor.model_policy import validate_model_id
from finding_extractor.models import (
    JobWarningPayload,
    ReliabilityMode,
    ReportExtraction,
    WarningReasonCategory,
)
from finding_extractor.providers import resolve_effective_reasoning
from finding_extractor.semantic_chunking import ChunkingSettings
from finding_extractor.store import ExtractionStore
from finding_extractor.verbatim import verbatim_match

logger = structlog.get_logger(__name__)

STRICT_VALIDATION_FAILURE_ERROR = "extraction_failed:validation_failed"
STRICT_SECTION_FAILURE_ERROR = "extraction_failed:section_failures_remaining"


class ReliabilityContractError(Exception):
    """Raised when strict reliability mode must terminate a job as failed."""

    def __init__(self, public_error: str, warning_payload: JobWarningPayload) -> None:
        super().__init__(public_error)
        self.public_error = public_error
        self.warning_payload = warning_payload


def get_task_store(request: Annotated[Request, TaskiqDepends()]) -> ExtractionStore:
    """Task dependency that retrieves store from FastAPI app state."""
    return request.app.state.store


def _is_timeout_error(exc: Exception) -> bool:
    return isinstance(exc, TimeoutError) or type(exc).__name__ == "APITimeoutError"


def _flatten_exception_group(exc_group: BaseExceptionGroup[BaseException]) -> list[Exception]:
    flattened: list[Exception] = []
    for nested in exc_group.exceptions:
        if isinstance(nested, BaseExceptionGroup):
            flattened.extend(_flatten_exception_group(nested))
        elif isinstance(nested, Exception):
            flattened.append(nested)
    return flattened


def to_public_job_error(exc: Exception) -> str:
    """Return a stable, non-sensitive job error string for API responses."""
    if isinstance(exc, ValueError):
        return "extraction_failed:invalid_request"
    if isinstance(exc, FallbackExceptionGroup):
        fallback_errors = _flatten_exception_group(exc)
        if fallback_errors and all(_is_timeout_error(error) for error in fallback_errors):
            return "extraction_failed:model_timeout"
        if fallback_errors and all(
            isinstance(error, ModelAPIError) or _is_timeout_error(error)
            for error in fallback_errors
        ):
            return "extraction_failed:model_provider_error"
    if isinstance(exc, ModelAPIError):
        return "extraction_failed:model_provider_error"
    if isinstance(exc, UnexpectedModelBehavior):
        return "extraction_failed:model_output_validation_failed"
    if _is_timeout_error(exc):
        return "extraction_failed:model_timeout"
    return "extraction_failed:internal_error"


def _is_verbatim_match(report_text: str, span: str) -> bool:
    return verbatim_match(span, report_text)


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
    section_failure_count: int = 0,
) -> JobWarningPayload | None:
    reason_categories: list[WarningReasonCategory] = []
    if validation_error_count > 0:
        reason_categories.append("validation_failed")
    if dropped_findings_count > 0 or dropped_non_finding_count > 0:
        reason_categories.append("verbatim_mismatch")
    has_primary_warning = validation_error_count > 0 or (
        dropped_findings_count > 0 or dropped_non_finding_count > 0
    )
    if section_failure_count > 0:
        has_primary_warning = True
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
        section_failure_count=section_failure_count,
    )


def _log_reliability_contract_outcome(
    *,
    terminal_status: str,
    reliability_mode: ReliabilityMode,
    warning_payload: JobWarningPayload,
    public_error: str | None = None,
) -> None:
    logger.info(
        "Reliability contract outcome",
        terminal_status=terminal_status,
        reliability_mode=reliability_mode,
        public_error=public_error,
        reason_categories=list(warning_payload.reason_categories),
        dropped_findings_count=warning_payload.dropped_findings_count,
        dropped_non_finding_count=warning_payload.dropped_non_finding_count,
        validation_error_count=warning_payload.validation_error_count,
        coverage_warning_count=warning_payload.coverage_warning_count,
        section_failure_count=warning_payload.section_failure_count,
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
        effective_reasoning = resolve_effective_reasoning(model_name, reasoning)
        logger.info("Extraction model configuration validated", model_name=model_name)

        async def _status_cb(message: str) -> None:
            logger.debug("Extraction task status update", status_message=message)
            await store.update_job_status_message(job_id, message)

        settings = get_settings()
        chunking_settings = ChunkingSettings(
            enabled=settings.chunking_enabled,
            semantic_trigger_sentence_count=settings.chunking_semantic_trigger_sentence_count,
            semantic_embedding_model=settings.chunking_semantic_embedding_model,
            semantic_threshold=settings.chunking_semantic_threshold,
            semantic_chunk_size=settings.chunking_semantic_chunk_size,
            semantic_similarity_window=settings.chunking_semantic_similarity_window,
            semantic_skip_window=settings.chunking_semantic_skip_window,
            impression_list_chunking_enabled=settings.chunking_impression_list_chunking_enabled,
            impression_list_max_items_per_chunk=settings.chunking_impression_list_max_items_per_chunk,
            impression_list_min_items_per_chunk=settings.chunking_impression_list_min_items_per_chunk,
        )

        async def _apply_coding(extraction):
            from finding_extractor.coding_bridge import apply_coding

            coding_model = settings.coding_model or model_name
            return await apply_coding(
                extraction,
                adjudicate_ambiguous=settings.coding_adjudication_enabled,
                adjudicator_model=coding_model,
                adjudicator_reasoning=settings.coding_reasoning,
                max_concurrency=settings.coding_max_concurrency,
            )

        async def _review_chunks(*, report_text, extraction, units):
            return await review_extraction_units(
                report_text=report_text,
                extraction=extraction,
                units=units,
                model_name=settings.validator_model or model_name,
                reasoning=settings.validator_reasoning,
            )

        orchestrated = await run_orchestrated_extraction(
            report_text=report.report_text,
            exam_description=exam_description,
            model_name=model_name,
            reasoning=effective_reasoning,
            validate=validate,
            coding_enabled=settings.coding_enabled,
            emit_status=_status_cb,
            extract_findings_fn=extract_findings,
            validate_extraction_fn=validate_extraction,
            apply_coding_fn=_apply_coding if settings.coding_enabled else None,
            review_chunks_fn=_review_chunks
            if (
                settings.validator_review_enabled
                and settings.validator_model is not None
            )
            else None,
            max_subagent_concurrency=settings.extractor_max_subagent_concurrency,
            unit_repair_attempts=settings.extractor_chunk_repair_attempts,
            validator_reextract_attempts=settings.validator_reextract_attempts,
            chunking_settings=chunking_settings,
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
        pipeline_diagnostics = orchestrated.pipeline_diagnostics
        section_failure_count = pipeline_diagnostics.remaining_failed_units
        if pipeline_diagnostics.mode in {"modular", "v2"}:
            logger.info(
                "Orchestrator pipeline diagnostics",
                total_units=pipeline_diagnostics.total_units,
                initial_failed_units=pipeline_diagnostics.initial_failed_units,
                repaired_units=pipeline_diagnostics.repaired_units,
                remaining_failed_units=pipeline_diagnostics.remaining_failed_units,
                repair_attempts_used=pipeline_diagnostics.repair_attempts_used,
                total_unit_attempts=pipeline_diagnostics.total_unit_attempts,
                failed_unit_labels=list(pipeline_diagnostics.failed_unit_labels),
                failed_unit_error_types=list(pipeline_diagnostics.failed_unit_error_types),
                validator_requested_units=pipeline_diagnostics.validator_requested_units,
                validator_reextracted_units=pipeline_diagnostics.validator_reextracted_units,
            )
            if section_failure_count > 0:
                logger.warning(
                    "Modular extraction has unrecovered failed units",
                    reliability_mode=reliability_mode,
                    remaining_failed_units=section_failure_count,
                    failed_unit_labels=list(pipeline_diagnostics.failed_unit_labels),
                    failed_unit_error_types=list(pipeline_diagnostics.failed_unit_error_types),
                )
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
        coverage_warning_count = max(coverage_warning_count, section_failure_count)
        warning_payload = _build_warning_payload(
            reliability_mode=reliability_mode,
            dropped_findings_count=dropped_findings_count,
            dropped_non_finding_count=dropped_non_finding_count,
            validation_error_count=validation_error_count,
            coverage_warning_count=coverage_warning_count,
            section_failure_count=section_failure_count,
        )
        if reliability_mode == "strict" and warning_payload is not None:
            if validation_error_count > 0:
                _log_reliability_contract_outcome(
                    terminal_status="failed",
                    reliability_mode=reliability_mode,
                    warning_payload=warning_payload,
                    public_error=STRICT_VALIDATION_FAILURE_ERROR,
                )
                raise ReliabilityContractError(
                    STRICT_VALIDATION_FAILURE_ERROR,
                    warning_payload,
                )
            if section_failure_count > 0:
                _log_reliability_contract_outcome(
                    terminal_status="failed",
                    reliability_mode=reliability_mode,
                    warning_payload=warning_payload,
                    public_error=STRICT_SECTION_FAILURE_ERROR,
                )
                raise ReliabilityContractError(
                    STRICT_SECTION_FAILURE_ERROR,
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
            reasoning_effort=effective_reasoning,
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
            _log_reliability_contract_outcome(
                terminal_status="completed_with_warnings",
                reliability_mode=reliability_mode,
                warning_payload=warning_payload,
            )
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
