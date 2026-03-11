"""Worker-side extraction orchestration with chunk-scoped parallel execution."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from finding_extractor.extractor.chunking import (
    ChunkingSettings,
    SectionChunk,
    chunk_section_text,
)
from finding_extractor.extractor.report_sections import parse_report_sections
from finding_extractor.models import (
    ExamInfo,
    ExtractedReportFindings,
    ExtractionResult,
    ExtractionUsage,
    Finding,
    NonFindingText,
    PipelineDiagnostics,
    ValidationResult,
)

ExtractFindingsFn = Callable[..., Awaitable[ExtractionResult]]
ValidateExtractionFn = Callable[[str, ExtractedReportFindings], ValidationResult]
ProgressCallbackFn = Callable[[str], Awaitable[None]]
ReviewChunksFn = Callable[..., Awaitable["ExtractionReviewDecision"]]
ExtractExamInfoFn = Callable[..., Awaitable[ExamInfo]]
ExtractProblemType = Literal[
    "hallucination",
    "missed_finding",
    "wrong_presence",
    "over_specific_finding_name",
    "incorrect_blanket_negative",
    "incorrect_location",
    "other",
]


def format_stage_status(stage: str, detail: str) -> str:
    """Return a parseable stage status message."""
    return f"[stage:{stage}] {detail}"


@dataclass(frozen=True)
class OrchestrationResult:
    """Output bundle from the worker orchestration flow."""

    extraction: ExtractedReportFindings
    usage: ExtractionUsage | None
    validation_result: ValidationResult | None
    pipeline_diagnostics: PipelineDiagnostics


@dataclass(frozen=True)
class ReportChunk:
    """A chunk-scoped extraction block from findings/impression sections."""

    index: int
    section_name: str
    report_chunk_id: str
    text: str
    preceding_chunk_context: str | None = None
    following_chunk_context: str | None = None
    feedback: str | None = None


@dataclass(frozen=True)
class ChunkExtractionOutcome:
    """Result for one extraction chunk attempt."""

    chunk: ReportChunk
    attempt: int
    extraction: ExtractedReportFindings | None
    usage: ExtractionUsage | None
    error: Exception | None


@dataclass(frozen=True)
class ExtractionReviewProblem:
    """One validator-identified problem for a chunk review decision."""

    raw_extracted_finding_index: int | None
    extract_problem_type: ExtractProblemType
    problem_detail: str


@dataclass(frozen=True)
class ExtractionReviewDecision:
    """Single-chunk validator decision for targeted re-extraction."""

    report_chunk_id: str
    should_reextract: bool = False
    problems: tuple[ExtractionReviewProblem, ...] = ()
    rationale: str | None = None

    def build_feedback_text(self) -> str:
        """Build structured feedback text for retry chunk prompts."""
        lines = ["RE-EXTRACTION_FEEDBACK"]
        for idx, problem in enumerate(self.problems, start=1):
            finding_idx = (
                str(problem.raw_extracted_finding_index)
                if problem.raw_extracted_finding_index is not None
                else "null"
            )
            lines.extend(
                [
                    f"- problem_{idx}:",
                    f"  - raw_extracted_finding_index: {finding_idx}",
                    f"  - extract_problem_type: {problem.extract_problem_type}",
                    f"  - problem_detail: {problem.problem_detail}",
                ]
            )
        if self.rationale:
            lines.append(f"REVIEW_RATIONALE: {self.rationale}")
        return "\n".join(lines)


def _agent_status_detail(message: str) -> str:
    lowered = message.strip().lower()
    if lowered.startswith("calling model"):
        return "calling_model"
    if lowered.startswith("model call complete"):
        return "model_call_complete"
    if lowered.startswith("retrying"):
        return "model_retrying"
    return "agent_status"


async def _emit_stage_progress(emit_progress: ProgressCallbackFn, stage: str, detail: str) -> None:
    await emit_progress(format_stage_status(stage, detail))


def _build_section_chunks(report_text: str) -> list[ReportChunk]:
    parsed = parse_report_sections(report_text)
    if not parsed.sections:
        return []

    selected_sections = [s for s in parsed.sections if s.name in {"findings", "impression"}]
    if not selected_sections:
        return []

    lines = report_text.split("\n")
    name_counts: dict[str, int] = defaultdict(int)
    result: list[ReportChunk] = []
    for section in selected_sections:
        section_text = "\n".join(lines[section.start_line : section.end_line]).strip()
        if not section_text:
            continue
        name_counts[section.name] += 1
        result.append(
            ReportChunk(
                index=len(result),
                section_name=section.name,
                report_chunk_id=f"{section.name}_{name_counts[section.name]}",
                text=section_text,
            )
        )
    return result


def _tag_finding_source(finding: Finding, section_name: str) -> Finding:
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


def _finding_dedupe_key(finding: Finding) -> str:
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
    outcomes: list[ChunkExtractionOutcome],
) -> tuple[ExtractedReportFindings, ExtractionUsage | None]:
    successful = [o for o in outcomes if o.extraction is not None]
    if not successful:
        raise RuntimeError("No successful section extractions to merge.")

    first_extraction = successful[0].extraction
    assert first_extraction is not None
    exam_info = first_extraction.exam_info
    findings: list[Finding] = []
    finding_index: dict[str, int] = {}
    non_findings: list[NonFindingText] = []
    non_finding_seen: set[tuple[str, str]] = set()

    for outcome in successful:
        extraction = outcome.extraction
        assert extraction is not None

        for finding in extraction.findings:
            tagged = _tag_finding_source(finding, outcome.chunk.section_name)
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
        ExtractedReportFindings(
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
    chunk: ReportChunk,
    attempt: int,
    stage: str,
    study_description: str | None,
    model_name: str,
    reasoning: str | None,
    emit_progress: ProgressCallbackFn,
    extract_findings_fn: ExtractFindingsFn,
    subagent_timeout_seconds: float | None = None,
) -> ChunkExtractionOutcome:
    await _emit_stage_progress(
        emit_progress,
        stage,
        f"chunk={chunk.report_chunk_id} attempt={attempt} status=started section={chunk.section_name}",
    )

    async def _chunk_status_cb(message: str) -> None:
        await _emit_stage_progress(
            emit_progress,
            stage,
            f"chunk={chunk.report_chunk_id} attempt={attempt} status={_agent_status_detail(message)}",
        )

    try:
        if subagent_timeout_seconds is not None:
            async with asyncio.timeout(subagent_timeout_seconds):
                extraction_result = await extract_findings_fn(
                    report_text=chunk.text,
                    study_description=study_description,
                    model=model_name,
                    reasoning=reasoning,
                    section_name=chunk.section_name,
                    preceding_chunk_context=chunk.preceding_chunk_context,
                    following_chunk_context=chunk.following_chunk_context,
                    status_callback=_chunk_status_cb,
                    feedback=chunk.feedback,
                )
        else:
            extraction_result = await extract_findings_fn(
                report_text=chunk.text,
                study_description=study_description,
                model=model_name,
                reasoning=reasoning,
                section_name=chunk.section_name,
                preceding_chunk_context=chunk.preceding_chunk_context,
                following_chunk_context=chunk.following_chunk_context,
                status_callback=_chunk_status_cb,
                feedback=chunk.feedback,
            )
        await _emit_stage_progress(
            emit_progress,
            stage,
            (
                f"chunk={chunk.report_chunk_id} attempt={attempt} status=completed "
                f"findings={len(extraction_result.report_findings.findings)} "
                f"non_findings={len(extraction_result.report_findings.non_finding_text)}"
            ),
        )
        return ChunkExtractionOutcome(
            chunk=chunk,
            attempt=attempt,
            extraction=extraction_result.report_findings,
            usage=extraction_result.usage,
            error=None,
        )
    except Exception as exc:
        await _emit_stage_progress(
            emit_progress,
            stage,
            f"chunk={chunk.report_chunk_id} attempt={attempt} status=failed error={type(exc).__name__}",
        )
        return ChunkExtractionOutcome(
            chunk=chunk,
            attempt=attempt,
            extraction=None,
            usage=None,
            error=exc,
        )


async def _run_chunks_with_bounded_concurrency(
    *,
    chunks: list[ReportChunk],
    attempt: int,
    stage: str,
    max_concurrency: int,
    study_description: str | None,
    model_name: str,
    reasoning: str | None,
    emit_progress: ProgressCallbackFn,
    extract_findings_fn: ExtractFindingsFn,
    subagent_timeout_seconds: float | None = None,
) -> list[ChunkExtractionOutcome]:
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    results: list[ChunkExtractionOutcome] = []

    async def _run_chunk(report_chunk: ReportChunk) -> ChunkExtractionOutcome:
        async with semaphore:
            return await _run_section_attempt(
                chunk=report_chunk,
                attempt=attempt,
                stage=stage,
                study_description=study_description,
                model_name=model_name,
                reasoning=reasoning,
                emit_progress=emit_progress,
                extract_findings_fn=extract_findings_fn,
                subagent_timeout_seconds=subagent_timeout_seconds,
            )

    tasks = [asyncio.create_task(_run_chunk(report_chunk)) for report_chunk in chunks]
    for task in asyncio.as_completed(tasks):
        outcome = await task
        results.append(outcome)
    return results


def _as_passthrough_chunk(report_text: str) -> tuple[SectionChunk, ...]:
    if not report_text:
        return ()
    return (SectionChunk(start_index=0, end_index=len(report_text), text=report_text),)


def _chunk_id_label(base: str, index: int, count: int) -> str:
    if count == 1:
        return base
    return f"{base}_chunk_{index + 1}"


def _format_previous_chunk_extraction(extraction: ExtractedReportFindings) -> str:
    lines = [
        "PREVIOUS_CHUNK_EXTRACTION",
        "| raw_extracted_finding_index | finding_name | presence | body_region | specific_location |",
        "|---|---|---|---|---|",
    ]
    if not extraction.findings:
        lines.append("| (none) | (none) | (none) | (none) | (none) |")
        return "\n".join(lines)

    for idx, finding in enumerate(extraction.findings):
        location = finding.location
        body_region = location.body_region if location is not None else ""
        specific_location = location.specific_anatomy if location is not None else ""
        lines.append(
            "| "
            f"{idx} | "
            f"{finding.finding_name.replace('|', '/')} | "
            f"{finding.presence.replace('|', '/')} | "
            f"{body_region.replace('|', '/')} | "
            f"{(specific_location or '').replace('|', '/')} |"
        )
    return "\n".join(lines)


async def _expand_chunks_with_semantic_chunking(
    *,
    section_chunks: list[ReportChunk],
    chunking_settings: ChunkingSettings,
    emit_progress: ProgressCallbackFn,
) -> tuple[list[ReportChunk], int]:
    """Expand section-level chunks into sub-chunks with adjacency context."""
    expanded: list[ReportChunk] = []
    degraded_sections = 0

    for section_chunk in section_chunks:
        result = await chunk_section_text(
            section_name=section_chunk.section_name,
            section_text=section_chunk.text,
            settings=chunking_settings,
        )
        chunks = result.chunks or _as_passthrough_chunk(section_chunk.text)
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
                ReportChunk(
                    index=len(expanded),
                    section_name=section_chunk.section_name,
                    report_chunk_id=_chunk_id_label(section_chunk.report_chunk_id, i, len(texts)),
                    text=chunk_text,
                    preceding_chunk_context=prev_context,
                    following_chunk_context=next_context,
                )
            )

        warning_detail = ""
        if warnings:
            warning_detail = f" warnings={','.join(warnings)}"
        await _emit_stage_progress(
            emit_progress,
            "sectionize",
            (
                f"chunk section={section_chunk.report_chunk_id} strategy={strategy} chunks={len(chunks)} "
                f"sentences={sentence_count} semantic_applied={str(semantic_applied).lower()}"
                f"{warning_detail}"
            ),
        )

    return expanded, degraded_sections


def _outcomes_to_chunk_map(
    outcomes: list[ChunkExtractionOutcome],
) -> dict[str, ChunkExtractionOutcome]:
    return {
        outcome.chunk.report_chunk_id: outcome
        for outcome in outcomes
        if outcome.extraction is not None
    }


def _collect_failed_metadata(
    pending_failed_chunks: list[ReportChunk],
    chunk_last_error_type: dict[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not pending_failed_chunks:
        return (), ()
    ordered_pending = sorted(pending_failed_chunks, key=lambda c: c.index)
    failed_chunk_ids = tuple(c.report_chunk_id for c in ordered_pending)
    failed_error_types = tuple(
        sorted(
            {chunk_last_error_type.get(c.report_chunk_id, "UnknownError") for c in ordered_pending}
        )
    )
    return failed_chunk_ids, failed_error_types


async def run_orchestrated_extraction(
    *,
    report_text: str,
    study_description: str | None,
    model_name: str,
    reasoning: str | None,
    validate: bool,
    emit_progress: ProgressCallbackFn,
    extract_findings_fn: ExtractFindingsFn,
    validate_extraction_fn: ValidateExtractionFn,
    review_chunks_fn: ReviewChunksFn | None = None,
    extract_exam_info_fn: ExtractExamInfoFn | None = None,
    source_ref: str | None = None,
    external_metadata: dict[str, str] | None = None,
    max_subagent_concurrency: int = 5,
    chunk_repair_attempts: int = 1,
    reviewer_reextract_enabled: bool = True,
    chunking_settings: ChunkingSettings | None = None,
    subagent_timeout_seconds: float | None = None,
    logger=None,
) -> OrchestrationResult:
    """Run extraction in V2 chunk-scoped stages."""

    base_chunks = _build_section_chunks(report_text)
    if not base_chunks:
        raise ValueError("No extractable `findings` or `impression` sections found in report text.")

    if chunking_settings is None:
        chunking_settings = ChunkingSettings()

    chunks, chunking_degraded_sections = await _expand_chunks_with_semantic_chunking(
        section_chunks=base_chunks,
        chunking_settings=chunking_settings,
        emit_progress=emit_progress,
    )

    unique_section_names = sorted({c.section_name for c in chunks})
    await _emit_stage_progress(
        emit_progress,
        "sectionize",
        (
            f"mode=v2 sections={len(unique_section_names)} "
            f"chunks={len(chunks)} names={','.join(unique_section_names)} "
            "chunking=on "
            f"degraded_sections={chunking_degraded_sections}"
        ),
    )

    # Launch exam-info extraction in parallel with chunk extraction
    exam_info_task: asyncio.Task[ExamInfo] | None = None
    if extract_exam_info_fn is not None:
        await _emit_stage_progress(emit_progress, "extract_exam_info", "start")

        async def _run_exam_info() -> ExamInfo:
            return await extract_exam_info_fn(
                report_text=report_text,
                study_description=study_description,
                source_ref=source_ref,
                external_metadata=external_metadata,
            )

        exam_info_task = asyncio.create_task(_run_exam_info())

    await _emit_stage_progress(
        emit_progress,
        "extract_sections",
        f"start chunks={len(chunks)} max_concurrency={max(1, max_subagent_concurrency)}",
    )

    total_chunk_attempts = 0
    repair_attempts_used = 0
    chunk_last_error_type: dict[str, str] = {}

    first_pass = await _run_chunks_with_bounded_concurrency(
        chunks=chunks,
        attempt=1,
        stage="extract_sections",
        max_concurrency=max_subagent_concurrency,
        study_description=study_description,
        model_name=model_name,
        reasoning=reasoning,
        emit_progress=emit_progress,
        extract_findings_fn=extract_findings_fn,
        subagent_timeout_seconds=subagent_timeout_seconds,
    )
    total_chunk_attempts += len(first_pass)

    successful_outcomes = [outcome for outcome in first_pass if outcome.error is None]
    failed_outcomes = [outcome for outcome in first_pass if outcome.error is not None]
    for outcome in failed_outcomes:
        assert outcome.error is not None
        chunk_last_error_type[outcome.chunk.report_chunk_id] = type(outcome.error).__name__

    await _emit_stage_progress(
        emit_progress,
        "extract_sections",
        (
            f"summary total_chunks={len(chunks)} "
            f"successful_chunks={len(successful_outcomes)} "
            f"failed_chunks={len(failed_outcomes)} "
            f"total_attempts={total_chunk_attempts}"
        ),
    )

    pending_failed_chunks = [outcome.chunk for outcome in failed_outcomes]
    for attempt in range(1, max(0, chunk_repair_attempts) + 1):
        if not pending_failed_chunks:
            break
        repair_attempts_used += 1
        await _emit_stage_progress(
            emit_progress,
            "repair_failed_sections",
            (
                f"attempt={attempt} start chunks={len(pending_failed_chunks)} "
                f"max_concurrency={max(1, max_subagent_concurrency)}"
            ),
        )
        retry_outcomes = await _run_chunks_with_bounded_concurrency(
            chunks=pending_failed_chunks,
            attempt=attempt,
            stage="repair_failed_sections",
            max_concurrency=max_subagent_concurrency,
            study_description=study_description,
            model_name=model_name,
            reasoning=reasoning,
            emit_progress=emit_progress,
            extract_findings_fn=extract_findings_fn,
            subagent_timeout_seconds=subagent_timeout_seconds,
        )
        total_chunk_attempts += len(retry_outcomes)
        recovered_chunks = sum(1 for outcome in retry_outcomes if outcome.error is None)
        successful_outcomes.extend(outcome for outcome in retry_outcomes if outcome.error is None)
        pending_failed_chunks = [
            outcome.chunk for outcome in retry_outcomes if outcome.error is not None
        ]
        for outcome in retry_outcomes:
            if outcome.error is None:
                chunk_last_error_type.pop(outcome.chunk.report_chunk_id, None)
            else:
                chunk_last_error_type[outcome.chunk.report_chunk_id] = type(outcome.error).__name__
        await _emit_stage_progress(
            emit_progress,
            "repair_failed_sections",
            (
                f"attempt={attempt} summary attempted_chunks={len(retry_outcomes)} "
                f"recovered_chunks={recovered_chunks} "
                f"remaining_failed_chunks={len(pending_failed_chunks)} "
                f"total_attempts={total_chunk_attempts}"
            ),
        )

    if not successful_outcomes:
        # Clean up the exam-info task before raising: cancel if still running,
        # then always await to retrieve any exception (prevents "Task exception
        # was never retrieved" warnings).
        if exam_info_task is not None:
            if not exam_info_task.done():
                exam_info_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await exam_info_task
        first_error = next(
            (outcome.error for outcome in first_pass if outcome.error is not None), None
        )
        if first_error is None:
            raise RuntimeError("V2 pipeline produced no successful chunk outputs.")
        raise first_error

    if pending_failed_chunks:
        failed_chunk_ids, failed_error_types = _collect_failed_metadata(
            pending_failed_chunks,
            chunk_last_error_type,
        )
        await _emit_stage_progress(
            emit_progress,
            "repair_failed_sections",
            (
                f"remaining_failed_chunks={len(pending_failed_chunks)} "
                f"chunk_ids={','.join(failed_chunk_ids)} "
                f"errors={','.join(failed_error_types)}"
            ),
        )
    else:
        await _emit_stage_progress(
            emit_progress,
            "repair_failed_sections",
            f"all_chunks_succeeded total_chunks={len(chunks)} total_attempts={total_chunk_attempts}",
        )

    successful_outcomes.sort(key=lambda outcome: outcome.chunk.index)
    extraction, usage = _merge_extractions(successful_outcomes)

    await _emit_stage_progress(
        emit_progress,
        "merge_dedupe",
        (
            f"final_merge findings={len(extraction.findings)} "
            f"non_findings={len(extraction.non_finding_text)}"
        ),
    )

    # Await exam-info sub-agent result and update extraction
    if exam_info_task is not None:
        try:
            if subagent_timeout_seconds is not None:
                exam_info = await asyncio.wait_for(exam_info_task, timeout=subagent_timeout_seconds)
            else:
                exam_info = await exam_info_task
            extraction = extraction.model_copy(update={"exam_info": exam_info})
            await _emit_stage_progress(
                emit_progress,
                "extract_exam_info",
                (
                    f"completed modality={exam_info.modality} "
                    f"body_region={exam_info.body_region} "
                    f"body_part={exam_info.body_part} "
                    f"contrast={exam_info.contrast} "
                    f"laterality={exam_info.laterality}"
                ),
            )
        except Exception as exc:
            await _emit_stage_progress(
                emit_progress,
                "extract_exam_info",
                f"failed error={type(exc).__name__} (keeping placeholder exam_info)",
            )
            if logger is not None:
                logger.warning(
                    "Exam-info sub-agent failed (non-fatal): %s",
                    type(exc).__name__,
                    exc_info=True,
                )

    reviewer_requested_chunks = 0
    reviewer_reextracted_chunks = 0
    if review_chunks_fn is not None:
        await _emit_stage_progress(emit_progress, "review", "start")
        outcome_by_chunk_id = {
            outcome.chunk.report_chunk_id: outcome for outcome in successful_outcomes
        }
        decision_by_chunk_id: dict[str, ExtractionReviewDecision] = {}
        review_semaphore = asyncio.Semaphore(max(1, max_subagent_concurrency))

        async def _review_one_chunk(outcome: ChunkExtractionOutcome) -> None:
            chunk_id = outcome.chunk.report_chunk_id
            await _emit_stage_progress(
                emit_progress,
                "review",
                f"chunk_review_start report_chunk_id={chunk_id}",
            )
            try:
                async with review_semaphore:
                    if subagent_timeout_seconds is not None:
                        async with asyncio.timeout(subagent_timeout_seconds):
                            decision = await review_chunks_fn(
                                report_chunk_id=chunk_id,
                                section_name=outcome.chunk.section_name,
                                report_chunk=outcome.chunk.text,
                                preceding_chunk_context=outcome.chunk.preceding_chunk_context,
                                following_chunk_context=outcome.chunk.following_chunk_context,
                                chunk_extraction=outcome.extraction,
                                exam_info=extraction.exam_info,
                            )
                    else:
                        decision = await review_chunks_fn(
                            report_chunk_id=chunk_id,
                            section_name=outcome.chunk.section_name,
                            report_chunk=outcome.chunk.text,
                            preceding_chunk_context=outcome.chunk.preceding_chunk_context,
                            following_chunk_context=outcome.chunk.following_chunk_context,
                            chunk_extraction=outcome.extraction,
                            exam_info=extraction.exam_info,
                        )
            except Exception as exc:
                await _emit_stage_progress(
                    emit_progress,
                    "review",
                    (
                        f"chunk_review_decision report_chunk_id={chunk_id} "
                        "should_reextract=false problem_count=0 "
                        f"error={type(exc).__name__}"
                    ),
                )
                if logger is not None:
                    logger.warning(
                        "Review failed for chunk (non-fatal): %s",
                        chunk_id,
                        exc_info=True,
                    )
                return

            decision_by_chunk_id[chunk_id] = decision
            await _emit_stage_progress(
                emit_progress,
                "review",
                (
                    f"chunk_review_decision report_chunk_id={chunk_id} "
                    f"should_reextract={str(decision.should_reextract).lower()} "
                    f"problem_count={len(decision.problems)}"
                ),
            )

        review_tasks = [
            asyncio.create_task(_review_one_chunk(outcome))
            for outcome in successful_outcomes
            if outcome.extraction is not None
        ]
        if review_tasks:
            await asyncio.gather(*review_tasks)

        decisions = [
            decision_by_chunk_id[outcome.chunk.report_chunk_id]
            for outcome in sorted(successful_outcomes, key=lambda o: o.chunk.index)
            if outcome.chunk.report_chunk_id in decision_by_chunk_id
        ]
        target_decisions = [decision for decision in decisions if decision.should_reextract]
        reviewer_requested_chunks = len(target_decisions)

        if target_decisions and not reviewer_reextract_enabled:
            await _emit_stage_progress(
                emit_progress,
                "review",
                (
                    f"reextract_disabled requested={reviewer_requested_chunks} "
                    f"chunk_ids={','.join(d.report_chunk_id for d in target_decisions)}"
                ),
            )
        elif target_decisions:
            retry_chunks: list[ReportChunk] = []
            for decision in target_decisions:
                prior_outcome = outcome_by_chunk_id.get(decision.report_chunk_id)
                if prior_outcome is None or prior_outcome.extraction is None:
                    continue
                base_chunk = prior_outcome.chunk
                feedback = (
                    f"{_format_previous_chunk_extraction(prior_outcome.extraction)}\n\n"
                    f"{decision.build_feedback_text()}"
                )
                retry_chunks.append(
                    ReportChunk(
                        index=base_chunk.index,
                        section_name=base_chunk.section_name,
                        report_chunk_id=base_chunk.report_chunk_id,
                        text=base_chunk.text,
                        preceding_chunk_context=base_chunk.preceding_chunk_context,
                        following_chunk_context=base_chunk.following_chunk_context,
                        feedback=feedback,
                    )
                )
                await _emit_stage_progress(
                    emit_progress,
                    "review",
                    f"chunk_reextract_start report_chunk_id={base_chunk.report_chunk_id}",
                )
            if retry_chunks:
                retry_outcomes = await _run_chunks_with_bounded_concurrency(
                    chunks=retry_chunks,
                    attempt=1,
                    stage="review",
                    max_concurrency=max_subagent_concurrency,
                    study_description=study_description,
                    model_name=model_name,
                    reasoning=reasoning,
                    emit_progress=emit_progress,
                    extract_findings_fn=extract_findings_fn,
                    subagent_timeout_seconds=subagent_timeout_seconds,
                )
                total_chunk_attempts += len(retry_outcomes)
                successful_by_chunk_id = _outcomes_to_chunk_map(successful_outcomes)
                for outcome in retry_outcomes:
                    if outcome.error is None and outcome.extraction is not None:
                        successful_by_chunk_id[outcome.chunk.report_chunk_id] = outcome
                        reviewer_reextracted_chunks += 1
                    await _emit_stage_progress(
                        emit_progress,
                        "review",
                        (
                            f"chunk_reextract_complete report_chunk_id={outcome.chunk.report_chunk_id} "
                            f"status={'success' if outcome.error is None else 'failed'}"
                        ),
                    )
                successful_outcomes = sorted(
                    successful_by_chunk_id.values(), key=lambda outcome: outcome.chunk.index
                )
                extraction, usage = _merge_extractions(successful_outcomes)

        await _emit_stage_progress(
            emit_progress,
            "review",
            (
                f"reviewed_chunks={len(decisions)} "
                f"reextract_chunks={reviewer_requested_chunks if reviewer_reextract_enabled else 0}"
            ),
        )

    failed_chunk_ids, failed_error_types = _collect_failed_metadata(
        pending_failed_chunks,
        chunk_last_error_type,
    )

    if validate:
        await _emit_stage_progress(emit_progress, "validate_output", "validating_extraction_results")
        validation_result = validate_extraction_fn(report_text, extraction)
    else:
        validation_result = None

    pipeline_diagnostics = PipelineDiagnostics(
        mode="modular",
        total_chunks=len(chunks),
        initial_failed_chunks=len(failed_outcomes),
        repaired_chunks=len(failed_outcomes) - len(pending_failed_chunks),
        remaining_failed_chunks=len(pending_failed_chunks),
        repair_attempts_used=repair_attempts_used,
        total_chunk_attempts=total_chunk_attempts,
        failed_chunk_ids=failed_chunk_ids,
        failed_chunk_error_types=failed_error_types,
        reviewer_requested_chunks=reviewer_requested_chunks,
        reviewer_reextracted_chunks=reviewer_reextracted_chunks,
    )

    return OrchestrationResult(
        extraction=extraction,
        usage=usage,
        validation_result=validation_result,
        pipeline_diagnostics=pipeline_diagnostics,
    )
