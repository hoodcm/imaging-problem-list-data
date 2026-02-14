"""Request/response models and mapping helpers for the API layer."""

from pydantic import ConfigDict, Field

from finding_extractor.base import StrictBaseModel
from finding_extractor.model_catalog import ModelCatalog
from finding_extractor.models import (
    CodingBridgeResult,
    CorrectionStatus,
    CorrectionType,
    ExtractedFinding,
    ExtractionUsage,
    JobStatus,
    ReportExtraction,
    ValidationResult,
)
from finding_extractor.store import (
    ExtractionStore,
    StoredCorrection,
    StoredExtraction,
    StoredExtractionDetail,
    StoredJob,
    StoredReport,
    StoredReportDetail,
    StoredUser,
)


class SubmitReportRequest(StrictBaseModel):
    """Payload for report create/upsert."""

    report_text: str = Field(min_length=1)
    source_ref: str | None = None
    patient_id: str | None = None


class ReportResponse(StrictBaseModel):
    """Summary response for report rows."""

    id: str
    text_hash: str
    source_ref: str | None = None
    patient_id: str | None = None
    created_at: str
    seen_before: bool = False


class ReportDetailResponse(StrictBaseModel):
    """Detailed report payload including text."""

    id: str
    text_hash: str
    report_text: str
    source_ref: str | None = None
    patient_id: str | None = None
    created_at: str


class TriggerExtractionRequest(StrictBaseModel):
    """Payload for queueing extraction."""

    model_config = ConfigDict(populate_by_name=True)

    model: str | None = None
    reasoning: str | None = None
    exam_description: str | None = None
    validate_output: bool = Field(default=True, alias="validate")


class TriggerExtractionResponse(StrictBaseModel):
    """Accepted job response for async extraction."""

    job_id: str
    report_id: str
    status: JobStatus


class JobResponse(StrictBaseModel):
    """Job polling response."""

    job_id: str
    report_id: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    extraction_id: str | None = None
    error: str | None = None
    status_message: str | None = None


class ExtractionSummaryResponse(StrictBaseModel):
    """Extraction list row."""

    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None = None
    created_at: str
    usage: ExtractionUsage | None = None
    coding_coded_count: int | None = None
    coding_unresolved_count: int | None = None


class ExtractionDetailResponse(StrictBaseModel):
    """Extraction detail payload."""

    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None = None
    exam_description_hint: str | None = None
    created_at: str
    extraction: ReportExtraction
    validation_result: ValidationResult | None = None
    usage: ExtractionUsage | None = None
    coding_result: CodingBridgeResult | None = None


class CreateCorrectionRequest(StrictBaseModel):
    """Payload for correction creation.

    Note: `created_by` is deprecated in favor of `username` for formal user attribution.
    """

    correction_type: CorrectionType
    target_finding_index: int | None = None
    target_json_path: str | None = None
    proposed_finding: ExtractedFinding | None = None
    attribute_overrides: dict[str, str] | None = None
    comment: str | None = None
    username: str
    status: CorrectionStatus = "pending"


class HealthResponse(StrictBaseModel):
    """Basic health/readiness response."""

    status: str


class UserResponse(StrictBaseModel):
    """User account for correction attribution."""

    username: str
    name: str
    email: str


class CorrectionResponse(StrictBaseModel):
    """Correction list/create response."""

    id: str
    extraction_id: str
    target_finding_index: int | None = None
    target_json_path: str | None = None
    correction_type: CorrectionType
    status: CorrectionStatus
    comment: str | None = None
    author: UserResponse | None = None
    created_by: str | None = None
    created_at: str


class AvailableModelResponse(StrictBaseModel):
    """Single selectable model returned from model discovery."""

    id: str
    provider: str
    tier: str
    is_default: bool = False


class ModelCatalogResponse(StrictBaseModel):
    """Model discovery response with cache freshness metadata."""

    updated_at: str
    stale: bool
    refresh_interval_seconds: int
    models: list[AvailableModelResponse]


def _report_response(report: StoredReport) -> ReportResponse:
    return ReportResponse(
        id=report.id,
        text_hash=report.text_hash,
        source_ref=report.source_ref,
        patient_id=report.patient_id,
        created_at=report.created_at,
        seen_before=report.seen_before,
    )


def _report_detail_response(report: StoredReportDetail) -> ReportDetailResponse:
    return ReportDetailResponse(
        id=report.id,
        text_hash=report.text_hash,
        report_text=report.report_text,
        source_ref=report.source_ref,
        patient_id=report.patient_id,
        created_at=report.created_at,
    )


def _job_response(job: StoredJob) -> JobResponse:
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
    )


def _extraction_summary_response(extraction: StoredExtraction) -> ExtractionSummaryResponse:
    return ExtractionSummaryResponse(
        id=extraction.id,
        report_id=extraction.report_id,
        model_name=extraction.model_name,
        reasoning_effort=extraction.reasoning_effort,
        created_at=extraction.created_at,
        usage=extraction.usage,
        coding_coded_count=extraction.coding_coded_count,
        coding_unresolved_count=extraction.coding_unresolved_count,
    )


def _extraction_detail_response(extraction: StoredExtractionDetail) -> ExtractionDetailResponse:
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
        coding_result=extraction.coding_result,
    )


def _user_response(user: StoredUser) -> UserResponse:
    return UserResponse(
        username=user.username,
        name=user.name,
        email=user.email,
    )


async def _correction_response(
    correction: StoredCorrection, store: ExtractionStore
) -> CorrectionResponse:
    """Map correction with author lookup.

    If correction has a username, fetch the user and populate author field.
    Otherwise, return None for author (legacy correction with only created_by).
    """
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


def map_report(report: StoredReport) -> ReportResponse:
    return _report_response(report)


def map_report_detail(report: StoredReportDetail) -> ReportDetailResponse:
    return _report_detail_response(report)


def map_job(job: StoredJob) -> JobResponse:
    return _job_response(job)


def map_extraction_summary(extraction: StoredExtraction) -> ExtractionSummaryResponse:
    return _extraction_summary_response(extraction)


def map_extraction_detail(extraction: StoredExtractionDetail) -> ExtractionDetailResponse:
    return _extraction_detail_response(extraction)


async def map_correction(
    correction: StoredCorrection, store: ExtractionStore
) -> CorrectionResponse:
    return await _correction_response(correction, store)


def map_correction_with_users(
    correction: StoredCorrection, user_map: dict[str, StoredUser]
) -> CorrectionResponse:
    """Map correction with pre-fetched user map (avoids N+1 queries).

    If correction has a username, look it up in the provided user_map.
    Otherwise, return None for author (legacy correction).
    """
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
            )
            for model in catalog.models
        ],
    )
