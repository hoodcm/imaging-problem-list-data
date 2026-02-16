"""Shared orchestrated extraction runtime used by worker and CLIs."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from finding_extractor.config import Settings, get_settings
from finding_extractor.extraction_agent import extract_findings, validate_extraction
from finding_extractor.extraction_orchestrator import (
    PipelineDiagnostics,
    format_stage_status,
    run_orchestrated_extraction,
)
from finding_extractor.extraction_review import review_extraction_units
from finding_extractor.model_policy import validate_model_id
from finding_extractor.models import (
    CodingBridgeResult,
    ExtractionUsage,
    JobWarningPayload,
    ReliabilityMode,
    ReportExtraction,
    ValidationResult,
    WarningReasonCategory,
)
from finding_extractor.providers import resolve_effective_reasoning
from finding_extractor.semantic_chunking import ChunkingSettings
from finding_extractor.store import ExtractionStore
from finding_extractor.verbatim import verbatim_match

logger = logging.getLogger(__name__)

STRICT_VALIDATION_FAILURE_ERROR = "extraction_failed:validation_failed"
STRICT_SECTION_FAILURE_ERROR = "extraction_failed:section_failures_remaining"

StatusCallback = Callable[[str], Awaitable[None]]
ExtractFindingsFn = Callable[..., Awaitable[object]]
ValidateExtractionFn = Callable[[str, ReportExtraction], ValidationResult]
ApplyCodingFn = Callable[[ReportExtraction], Awaitable[CodingBridgeResult]]
ReviewChunksFn = Callable[..., Awaitable[object]]


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
class RuntimeResult:
    """Unified runtime output for worker and CLI entrypoints."""

    extraction: ReportExtraction
    validation_result: ValidationResult | None
    usage: ExtractionUsage | None
    coding_result: CodingBridgeResult | None
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


async def _emit(status_callback: StatusCallback | None, stage: str, detail: str) -> None:
    if status_callback is None:
        return
    await status_callback(format_stage_status(stage, detail))


def _is_verbatim_match(report_text: str, span: str) -> bool:
    return verbatim_match(span, report_text)


def _drop_non_verbatim_segments(
    report_text: str,
    extraction: ReportExtraction,
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


def _build_chunking_settings(settings: Settings) -> ChunkingSettings:
    return ChunkingSettings(
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


async def run_extraction_runtime(
    report_text: str,
    *,
    exam_type: str | None,
    model: str | None,
    reasoning: str | None,
    validate: bool,
    reliability_mode: ReliabilityMode = "strict",
    store: ExtractionStore | None = None,
    db_path: Path | None = None,
    source_ref: str | None = None,
    report_id: str | None = None,
    status_callback: StatusCallback | None = None,
    settings: Settings | None = None,
    extract_findings_fn: ExtractFindingsFn = extract_findings,
    validate_extraction_fn: ValidateExtractionFn = validate_extraction,
    apply_coding_fn: ApplyCodingFn | None = None,
    review_chunks_fn: ReviewChunksFn | None = None,
) -> RuntimeResult:
    """Run orchestrated extraction with optional persistence and reliability policy."""

    resolved_settings = settings or get_settings()

    await _emit(status_callback, "preflight", "validating_model_configuration")
    model_name = model or resolved_settings.default_model
    validate_model_id(model_name)
    effective_reasoning = resolve_effective_reasoning(model_name, reasoning)

    async def _default_apply_coding(extraction: ReportExtraction) -> CodingBridgeResult:
        from finding_extractor.coding_bridge import apply_coding

        coding_model = resolved_settings.coding_model or model_name
        return await apply_coding(
            extraction,
            adjudicate_ambiguous=resolved_settings.coding_adjudication_enabled,
            adjudicator_model=coding_model,
            adjudicator_reasoning=resolved_settings.coding_reasoning,
            max_concurrency=resolved_settings.coding_max_concurrency,
        )

    async def _default_review_chunks(*, report_text: str, extraction: ReportExtraction, units):
        return await review_extraction_units(
            report_text=report_text,
            extraction=extraction,
            units=units,
            model_name=resolved_settings.validator_model or model_name,
            reasoning=resolved_settings.validator_reasoning,
        )

    selected_apply_coding = apply_coding_fn or _default_apply_coding
    selected_review_chunks = review_chunks_fn or _default_review_chunks

    orchestrated = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=exam_type,
        model_name=model_name,
        reasoning=effective_reasoning,
        validate=validate,
        coding_enabled=resolved_settings.coding_enabled,
        emit_status=(status_callback or (lambda _message: _noop_async())),
        extract_findings_fn=extract_findings_fn,
        validate_extraction_fn=validate_extraction_fn,
        apply_coding_fn=selected_apply_coding if resolved_settings.coding_enabled else None,
        review_chunks_fn=selected_review_chunks
        if (resolved_settings.validator_review_enabled and resolved_settings.validator_model is not None)
        else None,
        max_subagent_concurrency=resolved_settings.extractor_max_subagent_concurrency,
        unit_repair_attempts=resolved_settings.extractor_chunk_repair_attempts,
        validator_reextract_attempts=resolved_settings.validator_reextract_attempts,
        chunking_settings=_build_chunking_settings(resolved_settings),
        logger=logger,
    )

    extraction = orchestrated.extraction
    usage = orchestrated.usage
    validation_result = orchestrated.validation_result
    coding_result = orchestrated.coding_result
    pipeline_diagnostics = orchestrated.pipeline_diagnostics
    section_failure_count = pipeline_diagnostics.remaining_failed_units

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
        await _emit(status_callback, "persist", "saving_extraction_results")
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
            exam_description_hint=exam_type,
            validation_result=validation_result,
            usage=usage,
            coding_result=coding_result,
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
    await _emit(status_callback, terminal_stage, "extraction_complete")

    return RuntimeResult(
        extraction=extraction,
        validation_result=validation_result,
        usage=usage,
        coding_result=coding_result,
        pipeline_diagnostics=pipeline_diagnostics,
        model_name=model_name,
        reasoning_effort=effective_reasoning,
        warning_payload=warning_payload,
        storage_metadata=storage_metadata,
    )


async def _noop_async() -> None:
    return None
