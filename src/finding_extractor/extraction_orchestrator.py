"""Worker-side extraction orchestration with canonical stage status messages.

This module provides a structure-first orchestration layer for background jobs.
Behavior is intentionally equivalent to the legacy flow while introducing
explicit stage boundaries and stage-scoped status signaling.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from finding_extractor.models import (
    CodingBridgeResult,
    ExtractionResult,
    ExtractionUsage,
    ReportExtraction,
    ValidationResult,
)

ExtractFindingsFn = Callable[..., Awaitable[ExtractionResult]]
ValidateExtractionFn = Callable[[str, ReportExtraction], ValidationResult]
ApplyCodingFn = Callable[[ReportExtraction], Awaitable[CodingBridgeResult]]
EmitStatusFn = Callable[[str], Awaitable[None]]


def format_stage_status(stage: str, detail: str) -> str:
    """Return a parseable stage status message."""
    return f"[stage:{stage}] {detail}"


@dataclass(frozen=True)
class OrchestratedExtractionResult:
    """Output bundle from the worker orchestration flow."""

    extraction: ReportExtraction
    usage: ExtractionUsage | None
    validation_result: ValidationResult | None
    coding_result: CodingBridgeResult | None


def _agent_status_detail(message: str) -> str:
    lowered = message.strip().lower()
    if lowered.startswith("calling model"):
        return "calling_model"
    if lowered.startswith("model call complete"):
        return "model_call_complete"
    if lowered.startswith("retrying"):
        return "model_retrying"
    return "agent_status"


async def _emit_stage(emit_status: EmitStatusFn, stage: str, detail: str) -> None:
    await emit_status(format_stage_status(stage, detail))


async def run_orchestrated_extraction(
    *,
    report_text: str,
    exam_description: str | None,
    model_name: str,
    reasoning: str | None,
    validate: bool,
    coding_enabled: bool,
    emit_status: EmitStatusFn,
    extract_findings_fn: ExtractFindingsFn,
    validate_extraction_fn: ValidateExtractionFn,
    apply_coding_fn: ApplyCodingFn | None = None,
    logger=None,
) -> OrchestratedExtractionResult:
    """Run extraction in explicit stages while preserving legacy behavior."""
    await _emit_stage(emit_status, "sectionize", "legacy_single_pass")
    await _emit_stage(emit_status, "extract_sections", "start")

    async def _agent_status_cb(message: str) -> None:
        await _emit_stage(emit_status, "extract_sections", _agent_status_detail(message))

    extraction_result = await extract_findings_fn(
        report_text=report_text,
        exam_description=exam_description,
        model=model_name,
        reasoning=reasoning,
        status_callback=_agent_status_cb,
    )
    extraction = extraction_result.extraction
    usage = extraction_result.usage

    await _emit_stage(emit_status, "merge_dedupe", "legacy_passthrough")
    await _emit_stage(emit_status, "repair_failed_sections", "legacy_noop")

    if validate:
        await _emit_stage(emit_status, "validate_output", "validating_extraction_results")
        validation_result = validate_extraction_fn(report_text, extraction)
    else:
        validation_result = None

    coding_result = None
    if coding_enabled and apply_coding_fn is not None:
        await _emit_stage(emit_status, "apply_coding", "applying_oifm_coding")
        try:
            coding_result = await apply_coding_fn(extraction)
            if logger is not None:
                logger.info(
                    "Coding bridge complete",
                    coded=coding_result.coded_count,
                    unresolved=coding_result.unresolved_count,
                )
        except Exception:
            if logger is not None:
                logger.exception("Coding bridge failed (non-fatal)")
            coding_result = None

    return OrchestratedExtractionResult(
        extraction=extraction,
        usage=usage,
        validation_result=validation_result,
        coding_result=coding_result,
    )
