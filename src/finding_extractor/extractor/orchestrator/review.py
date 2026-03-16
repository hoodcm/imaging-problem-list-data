"""Per-chunk review and feedback-building helpers for the orchestrator."""

from __future__ import annotations

import asyncio

from finding_extractor.core.observability import observation_span
from finding_extractor.extractor.progress import ProgressCallbackType, emit_stage_progress
from finding_extractor.models import ExamInfo, ExtractedReportFindings

from .types import (
    ChunkExtractionOutcome,
    ExtractionReviewDecision,
    ReportChunk,
    ReviewChunksFn,
)


async def review_single_chunk(
    *,
    outcome: ChunkExtractionOutcome,
    exam_info: ExamInfo,
    review_chunks_fn: ReviewChunksFn,
    emit_progress: ProgressCallbackType,
    subagent_timeout_seconds: float | None = None,
    logger=None,
) -> ExtractionReviewDecision | None:
    """Review one chunk extraction. Returns decision or None on error (non-fatal)."""
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
            if subagent_timeout_seconds is not None:
                async with asyncio.timeout(subagent_timeout_seconds):
                    decision = await review_chunks_fn(
                        report_chunk_id=chunk_id,
                        section_name=outcome.chunk.section_name,
                        chunk_text=outcome.chunk.text,
                        preceding_chunk_context=outcome.chunk.preceding_chunk_context,
                        following_chunk_context=outcome.chunk.following_chunk_context,
                        chunk_extraction=outcome.extraction,
                        exam_info=exam_info,
                    )
            else:
                decision = await review_chunks_fn(
                    report_chunk_id=chunk_id,
                    section_name=outcome.chunk.section_name,
                    chunk_text=outcome.chunk.text,
                    preceding_chunk_context=outcome.chunk.preceding_chunk_context,
                    following_chunk_context=outcome.chunk.following_chunk_context,
                    chunk_extraction=outcome.extraction,
                    exam_info=exam_info,
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
            return None

        review_chunk_span.set_attribute(
            "should_reextract", str(decision.should_reextract)
        )
        review_chunk_span.set_attribute("problem_count", len(decision.problems))
        await emit_stage_progress(
            emit_progress,
            "review",
            (
                f"chunk_review_decision report_chunk_id={chunk_id} "
                f"should_reextract={str(decision.should_reextract).lower()} "
                f"problem_count={len(decision.problems)}"
            ),
        )
        return decision


def build_retry_chunk(
    chunk: ReportChunk,
    outcome: ChunkExtractionOutcome,
    decision: ExtractionReviewDecision,
) -> ReportChunk:
    """Build a chunk with reviewer feedback for corrective re-extraction."""
    assert outcome.extraction is not None, "Cannot build retry chunk without extraction"
    feedback = (
        f"{format_previous_chunk_extraction(outcome.extraction)}\n\n"
        f"{decision.build_feedback_text()}"
    )
    return ReportChunk(
        index=chunk.index,
        section_name=chunk.section_name,
        report_chunk_id=chunk.report_chunk_id,
        text=chunk.text,
        preceding_chunk_context=chunk.preceding_chunk_context,
        following_chunk_context=chunk.following_chunk_context,
        feedback=feedback,
    )


def format_previous_chunk_extraction(extraction: ExtractedReportFindings) -> str:
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
