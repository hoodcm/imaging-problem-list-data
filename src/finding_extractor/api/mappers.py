"""Mapping functions: Stored*/domain objects → API response models."""

from __future__ import annotations

import re

from finding_extractor.api.schemas import (
    AvailableModelResponse,
    CorrectionResponse,
    ExtractionDetailResponse,
    ExtractionSummaryResponse,
    JobResponse,
    ModelCatalogResponse,
    PipelineDiagnosticsResponse,
    ReportDetailResponse,
    ReportResponse,
    StatusEventResponse,
    UserResponse,
)
from finding_extractor.db.store import (
    ExtractionStore,
    StoredCorrection,
    StoredExtraction,
    StoredExtractionDetail,
    StoredJob,
    StoredReport,
    StoredReportDetail,
    StoredUser,
)
from finding_extractor.llm.catalog import ModelCatalog
from finding_extractor.models import PipelineDiagnostics


def _parse_status_event(message: str | None) -> StatusEventResponse | None:
    if message is None:
        return None
    trimmed = message.strip()
    if not trimmed:
        return None

    match = re.match(r"^\[stage:([a-z_]+)\]\s*(.*)$", trimmed, flags=re.IGNORECASE)
    if match is None:
        return None
    detail = match.group(2).strip() or None
    return StatusEventResponse(stage=match.group(1).lower(), detail=detail)


def map_report(report: StoredReport) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        text_hash=report.text_hash,
        source_ref=report.source_ref,
        patient_id=report.patient_id,
        created_at=report.created_at,
        seen_before=report.seen_before,
    )


def map_report_detail(report: StoredReportDetail) -> ReportDetailResponse:
    return ReportDetailResponse(
        id=report.id,
        text_hash=report.text_hash,
        report_text=report.report_text,
        source_ref=report.source_ref,
        patient_id=report.patient_id,
        created_at=report.created_at,
    )


def map_job(job: StoredJob) -> JobResponse:
    status_event = _parse_status_event(job.status_message)
    return JobResponse(
        job_id=job.id,
        report_id=job.report_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        extraction_id=job.extraction_id,
        error=job.error,
        status_message=job.status_message,
        status_event=status_event,
        warning_payload=job.warning_payload,
    )


def map_extraction_summary(extraction: StoredExtraction) -> ExtractionSummaryResponse:
    return ExtractionSummaryResponse(
        id=extraction.id,
        report_id=extraction.report_id,
        model_name=extraction.model_name,
        reasoning_effort=extraction.reasoning_effort,
        created_at=extraction.created_at,
        study_description=extraction.study_description,
        modality=extraction.modality,
        body_region=extraction.body_region,
        body_part=extraction.body_part,
        contrast=extraction.contrast,
        laterality=extraction.laterality,
        finding_count=extraction.finding_count,
        usage=extraction.usage,
        coding_coded_count=extraction.coding_coded_count,
        coding_unresolved_count=extraction.coding_unresolved_count,
    )


def _pipeline_diagnostics_response(
    diag: PipelineDiagnostics | None,
) -> PipelineDiagnosticsResponse | None:
    if diag is None:
        return None
    return PipelineDiagnosticsResponse(
        mode=diag.mode,
        total_chunks=diag.total_chunks,
        initial_failed_chunks=diag.initial_failed_chunks,
        repaired_chunks=diag.repaired_chunks,
        remaining_failed_chunks=diag.remaining_failed_chunks,
        repair_attempts_used=diag.repair_attempts_used,
        total_chunk_attempts=diag.total_chunk_attempts,
        failed_chunk_ids=list(diag.failed_chunk_ids),
        failed_chunk_error_types=list(diag.failed_chunk_error_types),
        reviewer_requested_chunks=diag.reviewer_requested_chunks,
        reviewer_reextracted_chunks=diag.reviewer_reextracted_chunks,
    )


def map_extraction_detail(extraction: StoredExtractionDetail) -> ExtractionDetailResponse:
    return ExtractionDetailResponse(
        id=extraction.id,
        report_id=extraction.report_id,
        model_name=extraction.model_name,
        reasoning_effort=extraction.reasoning_effort,
        exam_description_hint=extraction.exam_description_hint,
        created_at=extraction.created_at,
        extraction=extraction.extraction,
        validation_result=extraction.validation_result,
        usage=extraction.usage,
        pipeline_diagnostics=_pipeline_diagnostics_response(extraction.pipeline_diagnostics),
        trace_id=extraction.trace_id,
    )


def _user_response(user: StoredUser) -> UserResponse:
    return UserResponse(
        username=user.username,
        name=user.name,
        email=user.email,
    )


async def map_correction(
    correction: StoredCorrection, store: ExtractionStore
) -> CorrectionResponse:
    """Map correction with author lookup."""
    author = None
    if correction.username:
        user = await store.get_user(correction.username)
        if user:
            author = _user_response(user)

    return CorrectionResponse(
        id=correction.id,
        extraction_id=correction.extraction_id,
        target_finding_index=correction.target_finding_index,
        target_json_path=correction.target_json_path,
        correction_type=correction.correction_type,
        status=correction.status,
        comment=correction.comment,
        author=author,
        created_by=correction.created_by,
        created_at=correction.created_at,
    )


def map_correction_with_users(
    correction: StoredCorrection, user_map: dict[str, StoredUser]
) -> CorrectionResponse:
    """Map correction with pre-fetched user map (avoids N+1 queries)."""
    author = None
    if correction.username and correction.username in user_map:
        author = _user_response(user_map[correction.username])

    return CorrectionResponse(
        id=correction.id,
        extraction_id=correction.extraction_id,
        target_finding_index=correction.target_finding_index,
        target_json_path=correction.target_json_path,
        correction_type=correction.correction_type,
        status=correction.status,
        comment=correction.comment,
        author=author,
        created_by=correction.created_by,
        created_at=correction.created_at,
    )


def map_user(user: StoredUser) -> UserResponse:
    return _user_response(user)


def map_model_catalog(catalog: ModelCatalog) -> ModelCatalogResponse:
    return ModelCatalogResponse(
        updated_at=catalog.updated_at,
        stale=catalog.stale,
        refresh_interval_seconds=catalog.refresh_interval_seconds,
        models=[
            AvailableModelResponse(
                id=model.id,
                provider=model.provider,
                tier=model.tier,
                is_default=model.is_default,
                supported_reasoning=model.supported_reasoning,
                default_reasoning=model.default_reasoning,
            )
            for model in catalog.models
        ],
    )
