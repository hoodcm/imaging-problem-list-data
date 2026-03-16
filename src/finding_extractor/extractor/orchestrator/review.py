"""Review and targeted re-extraction helpers for the orchestrator."""

from __future__ import annotations

import asyncio

from finding_extractor.core.observability import observation_span
from finding_extractor.extractor.progress import ProgressCallbackType, emit_stage_progress
from finding_extractor.models import ExtractedReportFindings, ExtractionUsage

from .chunks import format_previous_chunk_extraction, run_chunks_with_bounded_concurrency
from .merge import merge_extractions, outcomes_to_chunk_map
from .types import (
    ChunkExtractionOutcome,
    ExtractFindingsFn,
    ExtractionReviewDecision,
    ReportChunk,
    ReviewChunksFn,
    ReviewPassResult,
)


async def run_review_pass(
    *,
    successful_outcomes: list[ChunkExtractionOutcome],
    extraction: ExtractedReportFindings,
    usage: ExtractionUsage | None,
    review_chunks_fn: ReviewChunksFn | None,
    reviewer_reextract_enabled: bool,
    max_subagent_concurrency: int,
    study_description: str | None,
    model_name: str,
    reasoning: str | None,
    emit_progress: ProgressCallbackType,
    extract_findings_fn: ExtractFindingsFn,
    subagent_timeout_seconds: float | None = None,
    logger=None,
) -> ReviewPassResult:
    """Run optional review and targeted chunk re-extraction."""
    reviewer_requested_chunks = 0
    reviewer_reextracted_chunks = 0
    additional_chunk_attempts = 0

    if review_chunks_fn is None:
        return ReviewPassResult(
            successful_outcomes=successful_outcomes,
            extraction=extraction,
            usage=usage,
            reviewer_requested_chunks=0,
            reviewer_reextracted_chunks=0,
            additional_chunk_attempts=0,
        )

    await emit_stage_progress(emit_progress, "review", "start")
    outcome_by_chunk_id = {
        outcome.chunk.report_chunk_id: outcome for outcome in successful_outcomes
    }
    decision_by_chunk_id: dict[str, ExtractionReviewDecision] = {}
    review_semaphore = asyncio.Semaphore(max(1, max_subagent_concurrency))

    async def _review_one_chunk(outcome: ChunkExtractionOutcome) -> None:
        chunk_id = outcome.chunk.report_chunk_id
        await emit_stage_progress(
            emit_progress,
            "review",
            f"chunk_review_start report_chunk_id={chunk_id}",
        )
        with observation_span(
            "extraction.review_chunk",
            chunk_id=chunk_id,
            section_name=outcome.chunk.section_name,
        ) as review_chunk_span:
            try:
                async with review_semaphore:
                    if subagent_timeout_seconds is not None:
                        async with asyncio.timeout(subagent_timeout_seconds):
                            decision = await review_chunks_fn(
                                report_chunk_id=chunk_id,
                                section_name=outcome.chunk.section_name,
                                chunk_text=outcome.chunk.text,
                                preceding_chunk_context=outcome.chunk.preceding_chunk_context,
                                following_chunk_context=outcome.chunk.following_chunk_context,
                                chunk_extraction=outcome.extraction,
                                exam_info=extraction.exam_info,
                            )
                    else:
                        decision = await review_chunks_fn(
                            report_chunk_id=chunk_id,
                            section_name=outcome.chunk.section_name,
                            chunk_text=outcome.chunk.text,
                            preceding_chunk_context=outcome.chunk.preceding_chunk_context,
                            following_chunk_context=outcome.chunk.following_chunk_context,
                            chunk_extraction=outcome.extraction,
                            exam_info=extraction.exam_info,
                        )
            except Exception as exc:
                review_chunk_span.set_attribute("status", "error")
                review_chunk_span.set_attribute("error_type", type(exc).__name__)
                await emit_stage_progress(
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

            review_chunk_span.set_attribute(
                "should_reextract", str(decision.should_reextract)
            )
            review_chunk_span.set_attribute("problem_count", len(decision.problems))
            decision_by_chunk_id[chunk_id] = decision
            await emit_stage_progress(
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

    # Reextract can be silently disabled via config; reviewer feedback is logged but not acted on.
    if target_decisions and not reviewer_reextract_enabled:
        await emit_stage_progress(
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
                f"{format_previous_chunk_extraction(prior_outcome.extraction)}\n\n"
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
            await emit_stage_progress(
                emit_progress,
                "review",
                f"chunk_reextract_start report_chunk_id={base_chunk.report_chunk_id}",
            )
        if retry_chunks:
            with observation_span(
                "extraction.chunks",
                stage="review_reextract",
                chunk_count=len(retry_chunks),
            ) as reextract_span:
                retry_outcomes = await run_chunks_with_bounded_concurrency(
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
                additional_chunk_attempts += len(retry_outcomes)
                successful_by_chunk_id = outcomes_to_chunk_map(successful_outcomes)
                for outcome in retry_outcomes:
                    if outcome.error is None and outcome.extraction is not None:
                        successful_by_chunk_id[outcome.chunk.report_chunk_id] = outcome
                        reviewer_reextracted_chunks += 1
                    await emit_stage_progress(
                        emit_progress,
                        "review",
                        (
                            f"chunk_reextract_complete report_chunk_id={outcome.chunk.report_chunk_id} "
                            f"status={'success' if outcome.error is None else 'failed'}"
                        ),
                    )
                reextract_span.set_attribute(
                    "reextracted_count", reviewer_reextracted_chunks
                )
                successful_outcomes = sorted(
                    successful_by_chunk_id.values(), key=lambda outcome: outcome.chunk.index
                )
                extraction, usage = merge_extractions(successful_outcomes)

    await emit_stage_progress(
        emit_progress,
        "review",
        (
            f"reviewed_chunks={len(decisions)} "
            f"reextract_chunks={reviewer_requested_chunks if reviewer_reextract_enabled else 0}"
        ),
    )

    return ReviewPassResult(
        successful_outcomes=successful_outcomes,
        extraction=extraction,
        usage=usage,
        reviewer_requested_chunks=reviewer_requested_chunks,
        reviewer_reextracted_chunks=reviewer_reextracted_chunks,
        additional_chunk_attempts=additional_chunk_attempts,
    )
