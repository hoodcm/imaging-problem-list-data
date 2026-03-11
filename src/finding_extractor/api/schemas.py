"""Request/response models for the API layer."""

from pydantic import ConfigDict, Field

from finding_extractor.core.base_model import StrictBaseModel
from finding_extractor.models import (
    CorrectionStatus,
    CorrectionType,
    ExtractedReportFindings,
    ExtractionUsage,
    Finding,
    JobStatus,
    JobWarningPayload,
    ReliabilityMode,
    ValidationResult,
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
    reliability_mode: ReliabilityMode = "strict"
    validate_output: bool = Field(default=True, alias="validate")


class TriggerExtractionResponse(StrictBaseModel):
    """Accepted job response for async extraction."""

    job_id: str
    report_id: str
    status: JobStatus


class StatusEventResponse(StrictBaseModel):
    """Structured stage/status event parsed from worker status messages."""

    version: str = "v2"
    stage: str
    detail: str | None = None


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
    status_event: StatusEventResponse | None = None
    warning_payload: JobWarningPayload | None = None


class ExtractionSummaryResponse(StrictBaseModel):
    """Extraction list row."""

    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None = None
    created_at: str
    study_description: str
    finding_count: int
    modality: str | None = None
    body_region: str | None = None
    body_part: str | None = None
    contrast: str | None = None
    laterality: str | None = None
    usage: ExtractionUsage | None = None
    coding_coded_count: int | None = None
    coding_unresolved_count: int | None = None


class PipelineDiagnosticsResponse(StrictBaseModel):
    """Pipeline diagnostics from the extraction orchestrator."""

    mode: str
    total_chunks: int
    initial_failed_chunks: int
    repaired_chunks: int
    remaining_failed_chunks: int
    repair_attempts_used: int
    total_chunk_attempts: int
    failed_chunk_ids: list[str] = Field(default_factory=list)
    failed_chunk_error_types: list[str] = Field(default_factory=list)
    validator_requested_chunks: int = 0
    validator_reextracted_chunks: int = 0


class ExtractionDetailResponse(StrictBaseModel):
    """Extraction detail payload."""

    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None = None
    exam_description_hint: str | None = None
    created_at: str
    extraction: ExtractedReportFindings
    validation_result: ValidationResult | None = None
    usage: ExtractionUsage | None = None
    pipeline_diagnostics: PipelineDiagnosticsResponse | None = None
    trace_id: str | None = None


class CreateCorrectionRequest(StrictBaseModel):
    """Payload for correction creation.

    Note: `created_by` is deprecated in favor of `username` for formal user attribution.
    """

    correction_type: CorrectionType
    target_finding_index: int | None = None
    target_json_path: str | None = None
    proposed_finding: Finding | None = None
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
    supported_reasoning: list[str] = Field(default_factory=list)
    default_reasoning: str = "none"


class ModelCatalogResponse(StrictBaseModel):
    """Model discovery response with cache freshness metadata."""

    updated_at: str
    stale: bool
    refresh_interval_seconds: int
    models: list[AvailableModelResponse]
