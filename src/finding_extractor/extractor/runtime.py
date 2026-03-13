"""Shared orchestrated extraction runtime used by worker and CLIs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import structlog

from finding_extractor.core.config import ExtractorSettings, get_settings
from finding_extractor.core.observability import get_current_trace_id
from finding_extractor.db.store import ExtractionStore
from finding_extractor.extractor.agent import (
    extract_chunk_findings,
    validate_extraction,
)
from finding_extractor.extractor.chunking import ChunkingSettings
from finding_extractor.extractor.orchestrator import (
    ExtractionReviewDecision,
    run_orchestrated_extraction,
)
from finding_extractor.extractor.orchestrator.types import (
    ExtractExamInfoFn,
    ExtractFindingsFn,
    ReviewChunksFn,
    ValidateExtractionFn,
)
from finding_extractor.extractor.progress import ProgressCallbackType, emit_stage_progress
from finding_extractor.extractor.review import review_extraction_chunk
from finding_extractor.extractor.verbatim import verbatim_match
from finding_extractor.llm.model_settings import resolve_runtime_reasoning
from finding_extractor.llm.policy import validate_model_id
from finding_extractor.models import (
    ExamInfo,
    ExtractedReportFindings,
    ExtractionUsage,
    JobWarningPayload,
    PipelineDiagnostics,
    ReliabilityMode,
    ValidationResult,
    WarningReasonCategory,
)

logger = structlog.get_logger(__name__)

STRICT_VALIDATION_FAILURE_ERROR = "extraction_failed:validation_failed"
STRICT_SECTION_FAILURE_ERROR = "extraction_failed:section_failures_remaining"


class ReliabilityContractError(Exception):
    """Raised when strict reliability mode must fail extraction."""

    def __init__(self, public_error: str, warning_payload: JobWarningPayload) -> None:
        super().__init__(public_error)
        self.public_error = public_error
        self.warning_payload = warning_payload


@dataclass(frozen=True)
class StorageMetadata:
    """Persistence metadata returned from a runtime extraction run."""

    db_path: str
    report_id: str
    report_seen_before: bool
    extraction_id: str
    model_name: str
    reasoning_effort: str | None
    extracted_at: str
    usage: ExtractionUsage | None = None


@dataclass(frozen=True)
class PipelineRunResult:
    """Unified runtime output for worker and CLI entrypoints."""

    extraction: ExtractedReportFindings
    validation_result: ValidationResult | None
    usage: ExtractionUsage | None
    pipeline_diagnostics: PipelineDiagnostics
    model_name: str
    reasoning_effort: str | None
    warning_payload: JobWarningPayload | None
    storage_metadata: StorageMetadata | None


def resolve_model_name(model: str | None) -> str:
    """Resolve effective model for extraction requests."""
    return model or get_settings().default_model


def resolve_db_path(db_path: Path | None) -> Path:
    """Resolve persistence path from option/env/default."""
    if db_path is not None:
        return db_path
    return get_settings().db_path


def _is_verbatim_match(report_text: str, span: str) -> bool:
    return verbatim_match(span, report_text)


def _drop_non_verbatim_segments(
    report_text: str,
    extraction: ExtractedReportFindings,
) -> tuple[ExtractedReportFindings, int, int]:
    kept_findings = [
        f for f in extraction.findings if _is_verbatim_match(report_text, f.report_text)
    ]
    kept_non_finding = [
        s for s in extraction.non_finding_text if _is_verbatim_match(report_text, s.text)
    ]
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
    section_failure_count: int,
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


def _build_chunking_settings(settings: ExtractorSettings) -> ChunkingSettings:
    return ChunkingSettings(
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


def _resolve_reviewer_model_name(
    *,
    extraction_model_name: str,
    settings: ExtractorSettings,
) -> str:
    """Resolve reviewer model and enforce model separation from extraction."""
    explicit_reviewer_model = settings.reviewer_model
    if explicit_reviewer_model is not None:
        if explicit_reviewer_model == extraction_model_name:
            msg = (
                "reviewer_model must differ from the extraction model "
                f"(both were {extraction_model_name!r})"
            )
            raise ValueError(msg)
        return explicit_reviewer_model

    fallback_model = settings.fallback_model
    if fallback_model is not None and fallback_model != extraction_model_name:
        return fallback_model

    msg = (
        "Reviewer review requires a model different from extraction model "
        f"{extraction_model_name!r}. Set IPL_REVIEWER_MODEL to a different model "
        "or configure IPL_FALLBACK_MODEL to a different model."
    )
    raise ValueError(msg)


def _build_review_callback(
    reviewer_model_name: str,
    reviewer_effective_reasoning: str | None,
) -> ReviewChunksFn:
    """Build a review-chunk callback with bound model config."""

    async def _review_chunks(
        *,
        report_chunk_id: str,
        section_name: str,
        chunk_text: str,
        preceding_chunk_context: str | None,
        following_chunk_context: str | None,
        chunk_extraction: ExtractedReportFindings,
        exam_info: ExamInfo,
    ) -> ExtractionReviewDecision:
        return await review_extraction_chunk(
            report_chunk_id=report_chunk_id,
            section_name=section_name,
            chunk_text=chunk_text,
            preceding_chunk_context=preceding_chunk_context,
            following_chunk_context=following_chunk_context,
            chunk_extraction=chunk_extraction,
            exam_info=exam_info,
            model_name=reviewer_model_name,
            reasoning=reviewer_effective_reasoning,
        )

    return _review_chunks


async def run_extraction_runtime(
    report_text: str,
    *,
    study_description: str | None,
    model: str | None,
    reasoning: str | None,
    validate: bool,
    reliability_mode: ReliabilityMode = "strict",
    store: ExtractionStore | None = None,
    db_path: Path | None = None,
    source_ref: str | None = None,
    report_id: str | None = None,
    progress_callback: ProgressCallbackType | None = None,
    settings: ExtractorSettings | None = None,
    extract_findings_fn: ExtractFindingsFn = extract_chunk_findings,
    validate_extraction_fn: ValidateExtractionFn = validate_extraction,
    review_chunks_fn: ReviewChunksFn | None = None,
    extract_exam_info_fn: ExtractExamInfoFn | None = None,
) -> PipelineRunResult:
    """Run orchestrated extraction with optional persistence and reliability policy."""

    resolved_settings = settings or get_settings()

    await emit_stage_progress(progress_callback, "preflight", "validating_model_configuration")
    model_name = model or resolved_settings.default_model
    validate_model_id(model_name)
    effective_reasoning = resolve_runtime_reasoning(
        model_name,
        reasoning,
        allow_unknown_model_reasoning=resolved_settings.allow_unknown_model_reasoning,
    )
    reviewer_model_name: str | None = None
    reviewer_effective_reasoning: str | None = None
    if resolved_settings.reviewer_enabled:
        reviewer_model_name = _resolve_reviewer_model_name(
            extraction_model_name=model_name,
            settings=resolved_settings,
        )
        reviewer_effective_reasoning = resolve_runtime_reasoning(
            reviewer_model_name,
            resolved_settings.reviewer_reasoning,
            allow_unknown_model_reasoning=resolved_settings.allow_unknown_model_reasoning,
        )

    async def _default_extract_exam_info(
        report_text: str,
        study_description: str | None = None,
        source_ref: str | None = None,
        external_metadata: dict[str, str] | None = None,
    ) -> ExamInfo:
        from finding_extractor.extractor.exam_info_agent import extract_exam_info

        return await extract_exam_info(
            report_text,
            study_description=study_description,
            source_ref=source_ref,
            external_metadata=external_metadata,
            model_name=model_name,
            reasoning=effective_reasoning,
        )

    if resolved_settings.reviewer_enabled and reviewer_model_name is not None:
        selected_review_chunks = review_chunks_fn or _build_review_callback(
            reviewer_model_name, reviewer_effective_reasoning,
        )
    else:
        selected_review_chunks = None
    selected_extract_exam_info = extract_exam_info_fn or _default_extract_exam_info
    exam_info_external_metadata: dict[str, str] | None = None
    if report_id is not None:
        exam_info_external_metadata = {"report_id": report_id}

    orchestrated = await run_orchestrated_extraction(
        report_text=report_text,
        study_description=study_description,
        model_name=model_name,
        reasoning=effective_reasoning,
        validate=validate,
        emit_progress=(progress_callback or _noop_progress),
        extract_findings_fn=extract_findings_fn,
        validate_extraction_fn=validate_extraction_fn,
        review_chunks_fn=selected_review_chunks,
        extract_exam_info_fn=selected_extract_exam_info,
        source_ref=source_ref,
        external_metadata=exam_info_external_metadata,
        max_subagent_concurrency=resolved_settings.extractor_max_subagent_concurrency,
        chunk_repair_attempts=1 if resolved_settings.extractor_chunk_repair_enabled else 0,
        reviewer_reextract_enabled=resolved_settings.reviewer_reextract_enabled,
        chunking_settings=_build_chunking_settings(resolved_settings),
        subagent_timeout_seconds=resolved_settings.subagent_timeout_seconds,
        logger=logger,
    )

    extraction = orchestrated.extraction
    usage = orchestrated.usage
    validation_result = orchestrated.validation_result
    pipeline_diagnostics = orchestrated.pipeline_diagnostics
    section_failure_count = pipeline_diagnostics.remaining_failed_chunks

    dropped_findings_count = 0
    dropped_non_finding_count = 0
    validation_error_count = 0
    coverage_warning_count = 0
    if validate and validation_result is not None:
        validation_error_count = len(validation_result.verbatim_errors)
        coverage_warning_count = len(validation_result.coverage_warnings)
        extraction, dropped_findings_count, dropped_non_finding_count = _drop_non_verbatim_segments(
            report_text,
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
            raise ReliabilityContractError(STRICT_VALIDATION_FAILURE_ERROR, warning_payload)
        if section_failure_count > 0:
            raise ReliabilityContractError(STRICT_SECTION_FAILURE_ERROR, warning_payload)

    storage_metadata: StorageMetadata | None = None
    if store is not None:
        await emit_stage_progress(progress_callback, "persist", "saving_extraction_results")
        resolved_db_path = resolve_db_path(db_path)
        report_seen_before = False
        target_report_id = report_id
        if target_report_id is None:
            report_record = await store.upsert_report(
                report_text=report_text,
                source_ref=source_ref,
            )
            target_report_id = report_record.id
            report_seen_before = report_record.seen_before

        extraction_record = await store.create_extraction(
            report_id=target_report_id,
            extraction=extraction,
            model_name=model_name,
            reasoning_effort=effective_reasoning,
            study_description_hint=study_description,
            validation_result=validation_result,
            usage=usage,
            pipeline_diagnostics=pipeline_diagnostics,
            trace_id=get_current_trace_id(),
        )
        storage_metadata = StorageMetadata(
            db_path=str(resolved_db_path),
            report_id=target_report_id,
            report_seen_before=report_seen_before,
            extraction_id=extraction_record.id,
            model_name=model_name,
            reasoning_effort=effective_reasoning,
            extracted_at=extraction_record.created_at,
            usage=usage,
        )

    terminal_stage = "completed_with_warnings" if warning_payload is not None else "completed"
    await emit_stage_progress(progress_callback, terminal_stage, "extraction_complete")

    return PipelineRunResult(
        extraction=extraction,
        validation_result=validation_result,
        usage=usage,
        pipeline_diagnostics=pipeline_diagnostics,
        model_name=model_name,
        reasoning_effort=effective_reasoning,
        warning_payload=warning_payload,
        storage_metadata=storage_metadata,
    )


async def _noop_progress(_message: str) -> None:
    """No-op progress callback used when no real callback is provided."""
