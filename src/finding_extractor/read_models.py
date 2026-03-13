"""Shared read models returned by the store and reused by API responses."""

from finding_extractor.core.base_model import StrictBaseModel
from finding_extractor.models import (
    ExtractedReportFindings,
    ExtractionUsage,
    PipelineDiagnostics,
    ValidationResult,
)


class ReportSummary(StrictBaseModel):
    """Summary view of a stored report."""

    id: str
    text_hash: str
    source_ref: str | None = None
    patient_id: str | None = None
    created_at: str
    seen_before: bool = False


class ReportDetail(StrictBaseModel):
    """Detailed view of a stored report."""

    id: str
    text_hash: str
    report_text: str
    source_ref: str | None = None
    patient_id: str | None = None
    created_at: str


class ExtractionSummary(StrictBaseModel):
    """Summary view of a stored extraction."""

    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None = None
    created_at: str
    study_description: str | None = None
    finding_count: int = 0
    modality: str | None = None
    body_region: str | None = None
    body_part: str | None = None
    contrast: str | None = None
    laterality: str | None = None
    usage: ExtractionUsage | None = None
    coded_finding_count: int | None = None
    unresolved_finding_count: int | None = None


class ExtractionDetail(StrictBaseModel):
    """Detailed view of a stored extraction."""

    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None = None
    study_description_hint: str | None = None
    created_at: str
    extraction: ExtractedReportFindings
    validation_result: ValidationResult | None = None
    usage: ExtractionUsage | None = None
    pipeline_diagnostics: PipelineDiagnostics | None = None
    trace_id: str | None = None
