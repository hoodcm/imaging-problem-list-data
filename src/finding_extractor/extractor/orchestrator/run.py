"""Worker-side extraction orchestration with chunk-scoped parallel execution."""

from __future__ import annotations

import asyncio
import contextlib

from finding_extractor.extractor.chunking import ChunkingSettings
from finding_extractor.extractor.progress import ProgressCallbackType, emit_stage_progress
from finding_extractor.models import ExamInfo, PipelineDiagnostics

from .chunks import (
    build_section_chunks,
    expand_chunks_with_semantic_chunking,
    run_chunks_with_bounded_concurrency,
)
from .merge import (
    collect_failed_metadata,
    merge_extractions,
)
from .review import run_review_pass
from .types import (
    ExtractExamInfoFn,
    ExtractFindingsFn,
    OrchestrationResult,
    ReviewChunksFn,
    ValidateExtractionFn,
)


async def run_orchestrated_extraction(
    *,
    report_text: str,
    study_description: str | None,
    model_name: str,
    reasoning: str | None,
    validate: bool,
    emit_progress: ProgressCallbackType,
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

    base_chunks = build_section_chunks(report_text)
    if not base_chunks:
        raise ValueError("No extractable `findings` or `impression` sections found in report text.")

    if chunking_settings is None:
        chunking_settings = ChunkingSettings()

    chunks, chunking_degraded_sections = await expand_chunks_with_semantic_chunking(
        section_chunks=base_chunks,
        chunking_settings=chunking_settings,
        emit_progress=emit_progress,
    )

    unique_section_names = sorted({c.section_name for c in chunks})
    await emit_stage_progress(
        emit_progress,
        "sectionize",
        (
            f"mode=v2 sections={len(unique_section_names)} "
            f"chunks={len(chunks)} names={','.join(unique_section_names)} "
            "chunking=on "
            f"degraded_sections={chunking_degraded_sections}"
        ),
    )

    exam_info_task: asyncio.Task[ExamInfo] | None = None
    if extract_exam_info_fn is not None:
        await emit_stage_progress(emit_progress, "extract_exam_info", "start")

        async def _run_exam_info() -> ExamInfo:
            return await extract_exam_info_fn(
                report_text=report_text,
                study_description=study_description,
                source_ref=source_ref,
                external_metadata=external_metadata,
            )

        exam_info_task = asyncio.create_task(_run_exam_info())

    await emit_stage_progress(
        emit_progress,
        "extract_sections",
        f"start chunks={len(chunks)} max_concurrency={max(1, max_subagent_concurrency)}",
    )

    total_chunk_attempts = 0
    repair_attempts_used = 0
    chunk_last_error_type: dict[str, str] = {}

    first_pass = await run_chunks_with_bounded_concurrency(
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

    await emit_stage_progress(
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
        await emit_stage_progress(
            emit_progress,
            "repair_failed_sections",
            (
                f"attempt={attempt} start chunks={len(pending_failed_chunks)} "
                f"max_concurrency={max(1, max_subagent_concurrency)}"
            ),
        )
        retry_outcomes = await run_chunks_with_bounded_concurrency(
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
        await emit_stage_progress(
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
        failed_chunk_ids, failed_error_types = collect_failed_metadata(
            pending_failed_chunks,
            chunk_last_error_type,
        )
        await emit_stage_progress(
            emit_progress,
            "repair_failed_sections",
            (
                f"remaining_failed_chunks={len(pending_failed_chunks)} "
                f"chunk_ids={','.join(failed_chunk_ids)} "
                f"errors={','.join(failed_error_types)}"
            ),
        )
    else:
        await emit_stage_progress(
            emit_progress,
            "repair_failed_sections",
            f"all_chunks_succeeded total_chunks={len(chunks)} total_attempts={total_chunk_attempts}",
        )

    successful_outcomes.sort(key=lambda outcome: outcome.chunk.index)
    extraction, usage = merge_extractions(successful_outcomes)

    await emit_stage_progress(
        emit_progress,
        "merge_dedupe",
        (
            f"final_merge findings={len(extraction.findings)} "
            f"non_findings={len(extraction.non_finding_text)}"
        ),
    )

    if exam_info_task is not None:
        try:
            if subagent_timeout_seconds is not None:
                exam_info = await asyncio.wait_for(exam_info_task, timeout=subagent_timeout_seconds)
            else:
                exam_info = await exam_info_task
            extraction = extraction.model_copy(update={"exam_info": exam_info})
            await emit_stage_progress(
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
            # Exam-info failure is non-fatal: pipeline continues with placeholder.
            await emit_stage_progress(
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

    review_result = await run_review_pass(
        successful_outcomes=successful_outcomes,
        extraction=extraction,
        usage=usage,
        review_chunks_fn=review_chunks_fn,
        reviewer_reextract_enabled=reviewer_reextract_enabled,
        max_subagent_concurrency=max_subagent_concurrency,
        study_description=study_description,
        model_name=model_name,
        reasoning=reasoning,
        emit_progress=emit_progress,
        extract_findings_fn=extract_findings_fn,
        subagent_timeout_seconds=subagent_timeout_seconds,
        logger=logger,
    )
    successful_outcomes = review_result.successful_outcomes
    extraction = review_result.extraction
    usage = review_result.usage
    total_chunk_attempts += review_result.additional_chunk_attempts

    failed_chunk_ids, failed_error_types = collect_failed_metadata(
        pending_failed_chunks,
        chunk_last_error_type,
    )

    if validate:
        await emit_stage_progress(emit_progress, "validate_output", "validating_extraction_results")
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
        reviewer_requested_chunks=review_result.reviewer_requested_chunks,
        reviewer_reextracted_chunks=review_result.reviewer_reextracted_chunks,
    )

    return OrchestrationResult(
        extraction=extraction,
        usage=usage,
        validation_result=validation_result,
        pipeline_diagnostics=pipeline_diagnostics,
    )

