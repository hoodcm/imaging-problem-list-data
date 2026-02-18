"""Worker-side extraction orchestration with chunk-scoped parallel execution."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from finding_extractor.coding_summary import inline_coding_counts
from finding_extractor.model_resilience import is_retryable_provider_error
from finding_extractor.models import (
    ExtractedFinding,
    ExtractionResult,
    ExtractionUsage,
    NonFindingText,
    ReportExtraction,
    ValidationResult,
)
from finding_extractor.report_sections import parse_report_sections
from finding_extractor.semantic_chunking import (
    ChunkingSettings,
    SectionChunk,
    chunk_section_text,
)

ExtractFindingsFn = Callable[..., Awaitable[ExtractionResult]]
ValidateExtractionFn = Callable[[str, ReportExtraction], ValidationResult]
ApplyCodingFn = Callable[[ReportExtraction], Awaitable[ReportExtraction]]
EmitStatusFn = Callable[[str], Awaitable[None]]
ReviewChunksFn = Callable[..., Awaitable["ValidationReviewDecision"]]


def format_stage_status(stage: str, detail: str) -> str:
    """Return a parseable stage status message."""
    return f"[stage:{stage}] {detail}"


@dataclass(frozen=True)
class OrchestratedExtractionResult:
    """Output bundle from the worker orchestration flow."""

    extraction: ReportExtraction
    usage: ExtractionUsage | None
    validation_result: ValidationResult | None
    pipeline_diagnostics: PipelineDiagnostics


@dataclass(frozen=True)
class SectionExtractionUnit:
    """A chunk-scoped extraction unit from findings/impression sections."""

    index: int
    section_name: str
    label: str
    report_text: str
    prev_context_text: str | None = None
    next_context_text: str | None = None


@dataclass(frozen=True)
class SectionExtractionOutcome:
    """Result for one extraction unit attempt."""

    unit: SectionExtractionUnit
    attempt: int
    extraction: ReportExtraction | None
    usage: ExtractionUsage | None
    error: Exception | None


@dataclass(frozen=True)
class ValidationReviewDecision:
    """LLM review output indicating target units for re-extraction."""

    reextract_unit_labels: tuple[str, ...] = ()
    rationale: str | None = None


@dataclass(frozen=True)
class PipelineDiagnostics:
    """Machine-parseable run diagnostics for stage/unit orchestration."""

    mode: str
    total_units: int
    initial_failed_units: int
    repaired_units: int
    remaining_failed_units: int
    repair_attempts_used: int
    total_unit_attempts: int
    failed_unit_labels: tuple[str, ...]
    failed_unit_error_types: tuple[str, ...]
    validator_requested_units: int = 0
    validator_reextracted_units: int = 0


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
        return []

    selected_sections = [s for s in parsed.sections if s.name in {"findings", "impression"}]
    if not selected_sections:
        return []

    lines = report_text.split("\n")
    name_counts: dict[str, int] = defaultdict(int)
    units: list[SectionExtractionUnit] = []
    for section in selected_sections:
        unit_text = "\n".join(lines[section.start_line : section.end_line]).strip()
        if not unit_text:
            continue
        name_counts[section.name] += 1
        units.append(
            SectionExtractionUnit(
                index=len(units),
                section_name=section.name,
                label=f"{section.name}_{name_counts[section.name]}",
                report_text=unit_text,
            )
        )
    return units


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
    payload["coding"] = None
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


def _normalize_span_text(value: str) -> str:
    """Normalize extracted span text for deterministic overlap checks."""
    return " ".join(value.split()).casefold()


def _merge_extractions(
    outcomes: list[SectionExtractionOutcome],
) -> tuple[ReportExtraction, ExtractionUsage | None]:
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

    finding_texts = {
        _normalize_span_text(finding.report_text)
        for finding in findings
        if finding.report_text and finding.report_text.strip()
    }
    filtered_non_findings = [
        non_finding
        for non_finding in non_findings
        if _normalize_span_text(non_finding.text) not in finding_texts
    ]

    merged_usage = _merge_usage([o.usage for o in successful])
    return (
        ReportExtraction(
            exam_info=exam_info,
            findings=findings,
            non_finding_text=filtered_non_findings,
        ),
        merged_usage,
    )


def _half_tail(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    mid = max(1, len(stripped) // 2)
    return stripped[-mid:].strip() or None


def _half_head(text: str) -> str | None:
    stripped = text.strip()
    if not stripped:
        return None
    mid = max(1, len(stripped) // 2)
    return stripped[:mid].strip() or None


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
        f"unit={unit.label} attempt={attempt} status=started section={unit.section_name}",
    )

    async def _unit_status_cb(message: str) -> None:
        await _emit_stage(
            emit_status,
            stage,
            f"unit={unit.label} attempt={attempt} status={_agent_status_detail(message)}",
        )

    try:
        call_kwargs = {
            "report_text": unit.report_text,
            "exam_description": exam_description,
            "model": model_name,
            "reasoning": reasoning,
            "section_name": unit.section_name,
            "prev_context_text": unit.prev_context_text,
            "next_context_text": unit.next_context_text,
            "unit_label": unit.label,
            "status_callback": _unit_status_cb,
        }
        signature = inspect.signature(extract_findings_fn)
        if any(
            parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in signature.parameters.values()
        ):
            filtered_kwargs = call_kwargs
        else:
            accepted = set(signature.parameters)
            filtered_kwargs = {
                key: value for key, value in call_kwargs.items() if key in accepted
            }

        extraction_result = await extract_findings_fn(**filtered_kwargs)
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
            attempt=attempt,
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
        return SectionExtractionOutcome(
            unit=unit,
            attempt=attempt,
            extraction=None,
            usage=None,
            error=exc,
        )


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
    on_outcome: Callable[[SectionExtractionOutcome], Awaitable[None]] | None = None,
) -> list[SectionExtractionOutcome]:
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    results: list[SectionExtractionOutcome] = []

    async def _run_unit(unit: SectionExtractionUnit) -> SectionExtractionOutcome:
        async with semaphore:
            return await _run_section_attempt(
                unit=unit,
                attempt=attempt,
                stage=stage,
                exam_description=exam_description,
                model_name=model_name,
                reasoning=reasoning,
                emit_status=emit_status,
                extract_findings_fn=extract_findings_fn,
            )

    tasks = [asyncio.create_task(_run_unit(unit)) for unit in units]
    for task in asyncio.as_completed(tasks):
        outcome = await task
        results.append(outcome)
        if on_outcome is not None:
            await on_outcome(outcome)
    return results


def _merge_inline_coding(
    *,
    extraction: ReportExtraction,
    outcomes: list[SectionExtractionOutcome],
    coding_by_label: dict[str, ReportExtraction],
) -> ReportExtraction:
    if not coding_by_label:
        return extraction

    keyed_coding: dict[str, object] = {}
    for outcome in outcomes:
        if outcome.extraction is None:
            continue
        coded_extraction = coding_by_label.get(outcome.unit.label)
        if coded_extraction is None:
            continue

        count = min(
            len(outcome.extraction.findings),
            len(coded_extraction.findings),
        )
        for idx in range(count):
            tagged = _tag_finding_source(
                outcome.extraction.findings[idx],
                outcome.unit.section_name,
            )
            key = _finding_dedupe_key(tagged)
            if key in keyed_coding:
                continue
            coded_bundle = coded_extraction.findings[idx].coding
            keyed_coding[key] = (
                coded_bundle.model_copy(deep=True) if coded_bundle is not None else None
            )

    if not keyed_coding:
        return extraction

    updated_findings: list[ExtractedFinding] = []
    for finding in extraction.findings:
        key = _finding_dedupe_key(finding)
        coding = keyed_coding.get(key)
        if coding is None:
            updated_findings.append(finding.model_copy(update={"coding": None}))
        else:
            updated_findings.append(finding.model_copy(update={"coding": coding}))
    return extraction.model_copy(update={"findings": updated_findings})


def _inline_coding_counts(extraction: ReportExtraction) -> tuple[int, int]:
    coded, unresolved = inline_coding_counts(extraction, unknown_if_absent=False)
    # unknown_if_absent=False guarantees ints.
    assert coded is not None and unresolved is not None
    return coded, unresolved


def _as_passthrough_chunk(report_text: str) -> tuple[SectionChunk, ...]:
    if not report_text:
        return ()
    return (SectionChunk(start_index=0, end_index=len(report_text), text=report_text),)


def _unit_label(base: str, index: int, count: int) -> str:
    if count == 1:
        return base
    return f"{base}_chunk_{index + 1}"


async def _expand_units_with_semantic_chunking(
    *,
    units: list[SectionExtractionUnit],
    chunking_settings: ChunkingSettings,
    emit_status: EmitStatusFn,
) -> tuple[list[SectionExtractionUnit], int]:
    """Expand section-level units into chunk sub-units with adjacency context."""
    expanded: list[SectionExtractionUnit] = []
    degraded_sections = 0

    for unit in units:
        result = await chunk_section_text(
            section_name=unit.section_name,
            section_text=unit.report_text,
            settings=chunking_settings,
        )
        chunks = result.chunks or _as_passthrough_chunk(unit.report_text)
        strategy = result.diagnostics.strategy
        warnings = result.diagnostics.warnings
        sentence_count = result.diagnostics.sentence_count
        semantic_applied = result.diagnostics.semantic_applied

        if "semantic_failed" in strategy:
            degraded_sections += 1

        texts = [chunk.text for chunk in chunks]
        for i, chunk_text in enumerate(texts):
            prev_context = _half_tail(texts[i - 1]) if i > 0 else None
            next_context = _half_head(texts[i + 1]) if i + 1 < len(texts) else None
            expanded.append(
                SectionExtractionUnit(
                    index=len(expanded),
                    section_name=unit.section_name,
                    label=_unit_label(unit.label, i, len(texts)),
                    report_text=chunk_text,
                    prev_context_text=prev_context,
                    next_context_text=next_context,
                )
            )

        warning_detail = ""
        if warnings:
            warning_detail = f" warnings={','.join(warnings)}"
        await _emit_stage(
            emit_status,
            "sectionize",
            (
                f"chunk unit={unit.label} strategy={strategy} chunks={len(chunks)} "
                f"sentences={sentence_count} semantic_applied={str(semantic_applied).lower()}"
                f"{warning_detail}"
            ),
        )

    return expanded, degraded_sections


def _outcomes_to_unit_map(
    outcomes: list[SectionExtractionOutcome],
) -> dict[str, SectionExtractionOutcome]:
    return {outcome.unit.label: outcome for outcome in outcomes if outcome.extraction is not None}


def _collect_failed_metadata(
    pending_failed_units: list[SectionExtractionUnit],
    unit_last_error_type: dict[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not pending_failed_units:
        return (), ()
    ordered_pending = sorted(pending_failed_units, key=lambda unit: unit.index)
    failed_labels = tuple(unit.label for unit in ordered_pending)
    failed_error_types = tuple(
        sorted({unit_last_error_type.get(unit.label, "UnknownError") for unit in ordered_pending})
    )
    return failed_labels, failed_error_types


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
    review_chunks_fn: ReviewChunksFn | None = None,
    max_subagent_concurrency: int = 5,
    unit_repair_attempts: int = 1,
    validator_reextract_enabled: bool = True,
    chunking_settings: ChunkingSettings | None = None,
    logger=None,
) -> OrchestratedExtractionResult:
    """Run extraction in V2 chunk-scoped stages."""

    base_units = _build_section_units(report_text)
    if not base_units:
        raise ValueError("No extractable `findings` or `impression` sections found in report text.")

    if chunking_settings is None:
        chunking_settings = ChunkingSettings()

    units, chunking_degraded_sections = await _expand_units_with_semantic_chunking(
        units=base_units,
        chunking_settings=chunking_settings,
        emit_status=emit_status,
    )

    unique_section_names = sorted({unit.section_name for unit in units})
    await _emit_stage(
        emit_status,
        "sectionize",
        (
            f"mode=v2 sections={len(unique_section_names)} "
            f"units={len(units)} names={','.join(unique_section_names)} "
            "chunking=on "
            f"degraded_sections={chunking_degraded_sections}"
        ),
    )

    await _emit_stage(
        emit_status,
        "extract_sections",
        f"start units={len(units)} max_concurrency={max(1, max_subagent_concurrency)}",
    )

    total_unit_attempts = 0
    repair_attempts_used = 0
    unit_last_error_type: dict[str, str] = {}
    coding_pipeline_enabled = coding_enabled and apply_coding_fn is not None
    coding_tasks: list[asyncio.Task[None]] = []
    coding_generation_by_label: dict[str, int] = {}
    latest_coding_by_label: dict[str, ReportExtraction] = {}
    coding_attempted_units = 0
    coding_completed_units = 0
    coding_failed_units = 0
    if coding_pipeline_enabled:
        await _emit_stage(emit_status, "apply_coding", "applying_oifm_coding")
        coding_semaphore = asyncio.Semaphore(max(1, max_subagent_concurrency))
        assert apply_coding_fn is not None

        async def _schedule_unit_coding(outcome: SectionExtractionOutcome) -> None:
            nonlocal coding_attempted_units, coding_completed_units, coding_failed_units
            if outcome.extraction is None:
                return

            extraction_snapshot = outcome.extraction
            label = outcome.unit.label
            generation = coding_generation_by_label.get(label, 0) + 1
            coding_generation_by_label[label] = generation
            coding_attempted_units += 1

            async def _run_coding() -> None:
                nonlocal coding_completed_units, coding_failed_units
                await _emit_stage(
                    emit_status,
                    "apply_coding",
                    f"unit={label} attempt={outcome.attempt} status=started",
                )
                started_at = time.monotonic()
                try:
                    async with coding_semaphore:
                        coded_extraction = await apply_coding_fn(extraction_snapshot)
                except Exception as exc:
                    coding_failed_units += 1
                    elapsed_ms = int((time.monotonic() - started_at) * 1000)
                    await _emit_stage(
                        emit_status,
                        "apply_coding",
                        (
                            f"unit={label} attempt={outcome.attempt} status=failed "
                            f"error={type(exc).__name__} elapsed_ms={elapsed_ms}"
                        ),
                    )
                    if logger is not None:
                        if is_retryable_provider_error(exc):
                            logger.warning(
                                "Coding bridge failed for unit (non-fatal, retryable): unit=%s attempt=%s error=%s",
                                label,
                                outcome.attempt,
                                type(exc).__name__,
                            )
                        else:
                            logger.exception(
                                "Coding bridge failed for unit (non-fatal): unit=%s attempt=%s",
                                label,
                                outcome.attempt,
                            )
                    return

                coding_completed_units += 1
                elapsed_ms = int((time.monotonic() - started_at) * 1000)
                if coding_generation_by_label.get(label) == generation:
                    latest_coding_by_label[label] = coded_extraction
                coded_count, unresolved_count = _inline_coding_counts(coded_extraction)
                await _emit_stage(
                    emit_status,
                    "apply_coding",
                    (
                        f"unit={label} attempt={outcome.attempt} status=completed "
                        f"coded={coded_count} "
                        f"unresolved={unresolved_count} "
                        f"elapsed_ms={elapsed_ms}"
                    ),
                )

            coding_tasks.append(asyncio.create_task(_run_coding()))

    else:

        async def _schedule_unit_coding(_outcome: SectionExtractionOutcome) -> None:
            return None

    first_pass = await _run_units_with_bounded_concurrency(
        units=units,
        attempt=1,
        stage="extract_sections",
        max_concurrency=max_subagent_concurrency,
        exam_description=exam_description,
        model_name=model_name,
        reasoning=reasoning,
        emit_status=emit_status,
        extract_findings_fn=extract_findings_fn,
        on_outcome=_schedule_unit_coding,
    )
    total_unit_attempts += len(first_pass)

    successful_outcomes = [outcome for outcome in first_pass if outcome.error is None]
    failed_outcomes = [outcome for outcome in first_pass if outcome.error is not None]
    for outcome in failed_outcomes:
        assert outcome.error is not None
        unit_last_error_type[outcome.unit.label] = type(outcome.error).__name__

    await _emit_stage(
        emit_status,
        "extract_sections",
        (
            f"summary total_units={len(units)} "
            f"successful_units={len(successful_outcomes)} "
            f"failed_units={len(failed_outcomes)} "
            f"total_attempts={total_unit_attempts}"
        ),
    )

    pending_failed_units = [outcome.unit for outcome in failed_outcomes]
    for attempt in range(1, max(0, unit_repair_attempts) + 1):
        if not pending_failed_units:
            break
        repair_attempts_used += 1
        await _emit_stage(
            emit_status,
            "repair_failed_sections",
            (
                f"attempt={attempt} start units={len(pending_failed_units)} "
                f"max_concurrency={max(1, max_subagent_concurrency)}"
            ),
        )
        retry_outcomes = await _run_units_with_bounded_concurrency(
            units=pending_failed_units,
            attempt=attempt,
            stage="repair_failed_sections",
            max_concurrency=max_subagent_concurrency,
            exam_description=exam_description,
            model_name=model_name,
            reasoning=reasoning,
            emit_status=emit_status,
            extract_findings_fn=extract_findings_fn,
            on_outcome=_schedule_unit_coding,
        )
        total_unit_attempts += len(retry_outcomes)
        recovered_units = sum(1 for outcome in retry_outcomes if outcome.error is None)
        successful_outcomes.extend(outcome for outcome in retry_outcomes if outcome.error is None)
        pending_failed_units = [
            outcome.unit for outcome in retry_outcomes if outcome.error is not None
        ]
        for outcome in retry_outcomes:
            if outcome.error is None:
                unit_last_error_type.pop(outcome.unit.label, None)
            else:
                unit_last_error_type[outcome.unit.label] = type(outcome.error).__name__
        await _emit_stage(
            emit_status,
            "repair_failed_sections",
            (
                f"attempt={attempt} summary attempted_units={len(retry_outcomes)} "
                f"recovered_units={recovered_units} "
                f"remaining_failed_units={len(pending_failed_units)} "
                f"total_attempts={total_unit_attempts}"
            ),
        )

    if not successful_outcomes:
        first_error = next(
            (outcome.error for outcome in first_pass if outcome.error is not None), None
        )
        if first_error is None:
            raise RuntimeError("V2 pipeline produced no successful chunk outputs.")
        raise first_error

    if pending_failed_units:
        failed_labels, failed_error_types = _collect_failed_metadata(
            pending_failed_units,
            unit_last_error_type,
        )
        await _emit_stage(
            emit_status,
            "repair_failed_sections",
            (
                f"remaining_failed_units={len(pending_failed_units)} "
                f"labels={','.join(failed_labels)} "
                f"errors={','.join(failed_error_types)}"
            ),
        )
    else:
        await _emit_stage(
            emit_status,
            "repair_failed_sections",
            f"all_units_succeeded total_units={len(units)} total_attempts={total_unit_attempts}",
        )

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

    validator_requested_units = 0
    validator_reextracted_units = 0
    if review_chunks_fn is not None:
        await _emit_stage(emit_status, "validator_review", "start")
        review_decision = await review_chunks_fn(
            report_text=report_text,
            extraction=extraction,
            units=tuple(units),
        )
        target_labels = tuple(dict.fromkeys(review_decision.reextract_unit_labels))
        validator_requested_units = len(target_labels)

        if target_labels and not validator_reextract_enabled:
            await _emit_stage(
                emit_status,
                "validator_review",
                (
                    f"reextract_disabled requested={len(target_labels)} "
                    f"labels={','.join(target_labels)}"
                ),
            )
        elif target_labels:
            await _emit_stage(
                emit_status,
                "validator_review",
                f"requested_reextract units={len(target_labels)} labels={','.join(target_labels)}",
            )
            unit_by_label = {unit.label: unit for unit in units}
            retry_units = [
                unit_by_label[label] for label in target_labels if label in unit_by_label
            ]
            if retry_units:
                retry_outcomes = await _run_units_with_bounded_concurrency(
                    units=retry_units,
                    attempt=1,
                    stage="validator_review",
                    max_concurrency=max_subagent_concurrency,
                    exam_description=exam_description,
                    model_name=model_name,
                    reasoning=reasoning,
                    emit_status=emit_status,
                    extract_findings_fn=extract_findings_fn,
                    on_outcome=_schedule_unit_coding,
                )
                total_unit_attempts += len(retry_outcomes)
                successful_by_label = _outcomes_to_unit_map(successful_outcomes)
                for outcome in retry_outcomes:
                    if outcome.error is None and outcome.extraction is not None:
                        successful_by_label[outcome.unit.label] = outcome
                        validator_reextracted_units += 1
                successful_outcomes = sorted(
                    successful_by_label.values(), key=lambda outcome: outcome.unit.index
                )
                extraction, usage = _merge_extractions(successful_outcomes)

                await _emit_stage(
                    emit_status,
                    "validator_review",
                    (
                        f"reextract_complete requested={validator_requested_units} "
                        f"reextracted={validator_reextracted_units}"
                    ),
                )
        else:
            await _emit_stage(emit_status, "validator_review", "no_reextract_requested")

    failed_labels, failed_error_types = _collect_failed_metadata(
        pending_failed_units,
        unit_last_error_type,
    )

    if validate:
        await _emit_stage(emit_status, "validate_output", "validating_extraction_results")
        validation_result = validate_extraction_fn(report_text, extraction)
    else:
        validation_result = None

    if coding_pipeline_enabled:
        if coding_tasks:
            await asyncio.gather(*coding_tasks)
        await _emit_stage(
            emit_status,
            "apply_coding",
            (
                f"summary attempted_units={coding_attempted_units} "
                f"completed_units={coding_completed_units} "
                f"failed_units={coding_failed_units}"
            ),
        )
        extraction = _merge_inline_coding(
            extraction=extraction,
            outcomes=successful_outcomes,
            coding_by_label=latest_coding_by_label,
        )
        if logger is not None:
            coded_count, unresolved_count = _inline_coding_counts(extraction)
            logger.info(
                "Coding bridge complete",
                coded=coded_count,
                unresolved=unresolved_count,
            )

    pipeline_diagnostics = PipelineDiagnostics(
        mode="modular",
        total_units=len(units),
        initial_failed_units=len(failed_outcomes),
        repaired_units=len(failed_outcomes) - len(pending_failed_units),
        remaining_failed_units=len(pending_failed_units),
        repair_attempts_used=repair_attempts_used,
        total_unit_attempts=total_unit_attempts,
        failed_unit_labels=failed_labels,
        failed_unit_error_types=failed_error_types,
        validator_requested_units=validator_requested_units,
        validator_reextracted_units=validator_reextracted_units,
    )

    return OrchestratedExtractionResult(
        extraction=extraction,
        usage=usage,
        validation_result=validation_result,
        pipeline_diagnostics=pipeline_diagnostics,
    )
