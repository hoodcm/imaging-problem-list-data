"""Worker-side extraction orchestration with canonical stage status messages.

This module provides a structure-first orchestration layer for background jobs.
Behavior is intentionally equivalent to the legacy flow while introducing
explicit stage boundaries and stage-scoped status signaling.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from finding_extractor.models import (
    CodingBridgeResult,
    ExtractedFinding,
    ExtractionResult,
    ExtractionUsage,
    NonFindingText,
    ReportExtraction,
    ValidationResult,
)
from finding_extractor.report_sections import parse_report_sections

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


@dataclass(frozen=True)
class SectionExtractionUnit:
    """A single section-scoped extraction unit."""

    index: int
    section_name: str
    label: str
    report_text: str


@dataclass(frozen=True)
class SectionExtractionOutcome:
    """Result for one section extraction attempt."""

    unit: SectionExtractionUnit
    extraction: ReportExtraction | None
    usage: ExtractionUsage | None
    error: Exception | None


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


def _build_section_units(report_text: str) -> list[SectionExtractionUnit]:
    parsed = parse_report_sections(report_text)
    if not parsed.sections:
        return [
            SectionExtractionUnit(
                index=0,
                section_name="full_report",
                label="full_report_1",
                report_text=report_text,
            )
        ]

    selected_sections = [s for s in parsed.sections if s.name in {"findings", "impression"}]
    if not selected_sections:
        selected_sections = list(parsed.sections)

    lines = report_text.split("\n")
    name_counts: dict[str, int] = defaultdict(int)
    units: list[SectionExtractionUnit] = []
    for i, section in enumerate(selected_sections):
        unit_text = "\n".join(lines[section.start_line : section.end_line]).strip()
        if not unit_text:
            continue
        name_counts[section.name] += 1
        units.append(
            SectionExtractionUnit(
                index=i,
                section_name=section.name,
                label=f"{section.name}_{name_counts[section.name]}",
                report_text=unit_text,
            )
        )

    if units:
        return units

    return [
        SectionExtractionUnit(
            index=0,
            section_name="full_report",
            label="full_report_1",
            report_text=report_text,
        )
    ]


def _tag_finding_source(finding: ExtractedFinding, section_name: str) -> ExtractedFinding:
    if finding.source_section is not None:
        return finding
    if section_name not in {"findings", "impression"}:
        return finding
    return finding.model_copy(update={"source_section": section_name})


def _merge_source_section(existing: str | None, incoming: str | None) -> str | None:
    if existing == "both" or incoming == "both":
        return "both"
    if existing is None:
        return incoming
    if incoming is None:
        return existing
    if existing == incoming:
        return existing
    if {existing, incoming} == {"findings", "impression"}:
        return "both"
    return existing


def _finding_dedupe_key(finding: ExtractedFinding) -> str:
    payload = finding.model_dump(mode="json")
    payload["source_section"] = None
    return json.dumps(payload, sort_keys=True)


def _merge_usage(usages: list[ExtractionUsage | None]) -> ExtractionUsage | None:
    present = [u for u in usages if u is not None]
    if not present:
        return None

    details: dict[str, int] = defaultdict(int)
    duration_total = 0
    saw_duration = False
    for usage in present:
        if usage.duration_ms is not None:
            duration_total += usage.duration_ms
            saw_duration = True
        for key, value in usage.details.items():
            details[key] += value

    return ExtractionUsage(
        requests=sum(u.requests for u in present),
        input_tokens=sum(u.input_tokens for u in present),
        output_tokens=sum(u.output_tokens for u in present),
        cache_read_tokens=sum(u.cache_read_tokens for u in present),
        cache_write_tokens=sum(u.cache_write_tokens for u in present),
        duration_ms=duration_total if saw_duration else None,
        details=dict(details),
    )


def _merge_extractions(outcomes: list[SectionExtractionOutcome]) -> tuple[ReportExtraction, ExtractionUsage | None]:
    successful = [o for o in outcomes if o.extraction is not None]
    if not successful:
        raise RuntimeError("No successful section extractions to merge.")

    first_extraction = successful[0].extraction
    assert first_extraction is not None
    exam_info = first_extraction.exam_info
    findings: list[ExtractedFinding] = []
    finding_index: dict[str, int] = {}
    non_findings: list[NonFindingText] = []
    non_finding_seen: set[tuple[str, str]] = set()

    for outcome in successful:
        extraction = outcome.extraction
        assert extraction is not None

        for finding in extraction.findings:
            tagged = _tag_finding_source(finding, outcome.unit.section_name)
            key = _finding_dedupe_key(tagged)
            if key in finding_index:
                existing_idx = finding_index[key]
                existing_finding = findings[existing_idx]
                merged_source = _merge_source_section(
                    existing_finding.source_section,
                    tagged.source_section,
                )
                if merged_source != existing_finding.source_section:
                    findings[existing_idx] = existing_finding.model_copy(
                        update={"source_section": merged_source}
                    )
                continue

            finding_index[key] = len(findings)
            findings.append(tagged)

        for non_finding in extraction.non_finding_text:
            key = (non_finding.category, non_finding.text)
            if key in non_finding_seen:
                continue
            non_finding_seen.add(key)
            non_findings.append(non_finding)

    merged_usage = _merge_usage([o.usage for o in successful])
    return (
        ReportExtraction(
            exam_info=exam_info,
            findings=findings,
            non_finding_text=non_findings,
        ),
        merged_usage,
    )


async def _run_section_attempt(
    *,
    unit: SectionExtractionUnit,
    attempt: int,
    stage: str,
    exam_description: str | None,
    model_name: str,
    reasoning: str | None,
    emit_status: EmitStatusFn,
    extract_findings_fn: ExtractFindingsFn,
) -> SectionExtractionOutcome:
    await _emit_stage(
        emit_status,
        stage,
        f"unit={unit.label} attempt={attempt} status=started",
    )

    async def _unit_status_cb(message: str) -> None:
        await _emit_stage(
            emit_status,
            stage,
            f"unit={unit.label} attempt={attempt} status={_agent_status_detail(message)}",
        )

    try:
        extraction_result = await extract_findings_fn(
            report_text=unit.report_text,
            exam_description=exam_description,
            model=model_name,
            reasoning=reasoning,
            status_callback=_unit_status_cb,
        )
        await _emit_stage(
            emit_status,
            stage,
            (
                f"unit={unit.label} attempt={attempt} status=completed "
                f"findings={len(extraction_result.extraction.findings)} "
                f"non_findings={len(extraction_result.extraction.non_finding_text)}"
            ),
        )
        return SectionExtractionOutcome(
            unit=unit,
            extraction=extraction_result.extraction,
            usage=extraction_result.usage,
            error=None,
        )
    except Exception as exc:
        await _emit_stage(
            emit_status,
            stage,
            f"unit={unit.label} attempt={attempt} status=failed error={type(exc).__name__}",
        )
        return SectionExtractionOutcome(unit=unit, extraction=None, usage=None, error=exc)


async def _run_units_with_bounded_concurrency(
    *,
    units: list[SectionExtractionUnit],
    attempt: int,
    stage: str,
    max_concurrency: int,
    exam_description: str | None,
    model_name: str,
    reasoning: str | None,
    emit_status: EmitStatusFn,
    extract_findings_fn: ExtractFindingsFn,
) -> list[SectionExtractionOutcome]:
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    results: list[SectionExtractionOutcome | None] = [None] * len(units)

    async def _run_indexed(idx: int, unit: SectionExtractionUnit) -> None:
        async with semaphore:
            results[idx] = await _run_section_attempt(
                unit=unit,
                attempt=attempt,
                stage=stage,
                exam_description=exam_description,
                model_name=model_name,
                reasoning=reasoning,
                emit_status=emit_status,
                extract_findings_fn=extract_findings_fn,
            )

    await asyncio.gather(*(_run_indexed(i, unit) for i, unit in enumerate(units)))
    return [result for result in results if result is not None]


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
    modular_pipeline_enabled: bool = False,
    section_max_concurrency: int = 2,
    section_repair_attempts: int = 1,
    logger=None,
) -> OrchestratedExtractionResult:
    """Run extraction in explicit stages while preserving legacy behavior."""
    if not modular_pipeline_enabled:
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
    else:
        units = _build_section_units(report_text)
        unique_section_names = sorted({unit.section_name for unit in units})
        await _emit_stage(
            emit_status,
            "sectionize",
            (
                f"mode=modular sections={len(unique_section_names)} "
                f"units={len(units)} names={','.join(unique_section_names)}"
            ),
        )
        await _emit_stage(
            emit_status,
            "extract_sections",
            f"start units={len(units)} max_concurrency={max(1, section_max_concurrency)}",
        )
        first_pass = await _run_units_with_bounded_concurrency(
            units=units,
            attempt=1,
            stage="extract_sections",
            max_concurrency=section_max_concurrency,
            exam_description=exam_description,
            model_name=model_name,
            reasoning=reasoning,
            emit_status=emit_status,
            extract_findings_fn=extract_findings_fn,
        )
        successful_outcomes = [outcome for outcome in first_pass if outcome.error is None]
        failed_outcomes = [outcome for outcome in first_pass if outcome.error is not None]

        await _emit_stage(
            emit_status,
            "merge_dedupe",
            (
                f"initial_merge successful_units={len(successful_outcomes)} "
                f"failed_units={len(failed_outcomes)}"
            ),
        )

        if failed_outcomes:
            await _emit_stage(
                emit_status,
                "repair_failed_sections",
                (
                    f"start failed_units={len(failed_outcomes)} "
                    f"max_attempts={max(0, section_repair_attempts)}"
                ),
            )
        else:
            await _emit_stage(emit_status, "repair_failed_sections", "no_failed_units")

        pending_failed_units = [outcome.unit for outcome in failed_outcomes]
        for attempt in range(1, max(0, section_repair_attempts) + 1):
            if not pending_failed_units:
                break
            retry_outcomes = await _run_units_with_bounded_concurrency(
                units=pending_failed_units,
                attempt=attempt,
                stage="repair_failed_sections",
                max_concurrency=section_max_concurrency,
                exam_description=exam_description,
                model_name=model_name,
                reasoning=reasoning,
                emit_status=emit_status,
                extract_findings_fn=extract_findings_fn,
            )
            successful_outcomes.extend(outcome for outcome in retry_outcomes if outcome.error is None)
            pending_failed_units = [
                outcome.unit for outcome in retry_outcomes if outcome.error is not None
            ]

        if pending_failed_units:
            await _emit_stage(
                emit_status,
                "repair_failed_sections",
                f"remaining_failed_units={len(pending_failed_units)}",
            )
            if logger is not None:
                logger.warning(
                    "Section repair exhausted; proceeding with successful units only",
                    remaining_failed_units=len(pending_failed_units),
                )
        else:
            await _emit_stage(emit_status, "repair_failed_sections", "all_units_succeeded")

        if not successful_outcomes:
            first_error = next((outcome.error for outcome in first_pass if outcome.error is not None), None)
            if first_error is None:
                raise RuntimeError("Modular pipeline produced no successful section outputs.")
            raise first_error

        # Keep merge deterministic regardless of transient retry timing.
        successful_outcomes.sort(key=lambda outcome: outcome.unit.index)
        extraction, usage = _merge_extractions(successful_outcomes)
        await _emit_stage(
            emit_status,
            "merge_dedupe",
            (
                f"final_merge findings={len(extraction.findings)} "
                f"non_findings={len(extraction.non_finding_text)}"
            ),
        )

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
