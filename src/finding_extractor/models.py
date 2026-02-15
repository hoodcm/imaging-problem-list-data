"""Pydantic models for radiology report finding extraction."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from pydantic import Field

from finding_extractor.base import StrictBaseModel

ReasoningLevel = Literal["none", "minimal", "low", "medium", "high"]

CorrectionType = Literal["add_finding", "update_finding", "comment"]
CorrectionStatus = Literal["pending", "accepted", "rejected", "applied"]
JobStatus = Literal["pending", "running", "completed", "completed_with_warnings", "failed"]
Presence = Literal["present", "absent", "indeterminate", "possible"]


class ExamInfo(StrictBaseModel):
    """Metadata about the imaging exam this extraction came from."""

    study_description: str = Field(
        description='Study description, e.g., "CT Abdomen and Pelvis WO contrast"'
    )
    study_date: date | None = Field(
        default=None,
        description="ISO date if known (YYYY-MM-DD)",
    )
    modality: str | None = Field(
        default=None,
        description='Modality code: "CT", "XR", "MR", "US", "NM", etc.',
    )
    body_part: str | None = Field(
        default=None,
        description='Body part examined: "abdomen", "chest", "brain", "shoulder", etc.',
    )


class FindingLocation(StrictBaseModel):
    """Where the finding is occurring.

    Separate from other attributes because location is often implied by the exam type
    rather than stated explicitly in the report text.
    """

    body_region: Literal[
        "chest",
        "abdomen",
        "pelvis",
        "head",
        "neck",
        "spine",
        "upper extremity",
        "lower extremity",
        "breast",
    ] = Field(
        description="Body region",
    )
    specific_anatomy: str | None = Field(
        default=None,
        description='Specific anatomy: "right lower lobe", "left kidney interpolar region", "T9 vertebral body"',
    )
    laterality: Literal["left", "right", "bilateral"] | None = Field(
        default=None,
        description="Laterality, or None if not applicable",
    )


class FindingAttribute(StrictBaseModel):
    """Any descriptive property of a finding beyond presence and location.

    Flexible key-value structure for attributes like size, acuity, change from prior,
    severity, count, and morphology.
    """

    key: str = Field(
        description='Attribute key: "size", "acuity", "change_from_prior", "severity", "count", "morphology"'
    )
    value: str = Field(
        description='Attribute value: "3 mm", "acute", "stable", "moderate", "2", "nonobstructing"'
    )


class ExtractedFinding(StrictBaseModel):
    """The core output model for each finding extracted from a radiology report.

    Key design points:
    - finding_name: concise, reusable clinical term (not a sentence)
    - presence: present/absent/indeterminate/possible. "possible" covers hedged language
      like "raising the possibility of", "suggestive of", "cannot exclude"
    - Both present and absent findings extracted ("no ascites" → ascites/absent)
    - report_text must be a verbatim excerpt — quote, not paraphrase
    - Multiple instances of same finding type → separate entries
    """

    finding_name: str = Field(
        description='Concise clinical term: "renal calculus", "hepatic steatosis"'
    )
    presence: Presence = Field(
        description="Presence status: present, absent, indeterminate, or possible (for hedged language)"
    )
    location: FindingLocation | None = Field(
        default=None,
        description="Location of the finding, if applicable",
    )
    attributes: list[FindingAttribute] = Field(
        default_factory=list,
        description="Descriptive attributes of the finding (size, acuity, change_from_prior, etc.)",
    )
    report_text: str = Field(
        description="Verbatim quote from the report text that supports this finding"
    )
    source_section: Literal["findings", "impression", "both"] | None = Field(
        default=None,
        description=(
            "Which report section this finding was extracted from: "
            '"findings" (body/comment), "impression" (impression/conclusion), '
            '"both" (mentioned in both sections). '
            "null if section boundaries cannot be determined."
        ),
    )


class NonFindingText(StrictBaseModel):
    """Segments of report text identified as not containing findings.

    This lets us account for every piece of text in the report — findings go into
    ExtractedFinding.report_text, everything else goes here.
    """

    text: str = Field(description="The verbatim text segment")
    category: Literal[
        "metadata",
        "technique",
        "indication",
        "comparison",
        "clinical_history",
        "impression",
        "other",
    ] = Field(
        description="Category of the non-finding text segment",
    )


class ReportExtraction(StrictBaseModel):
    """Top-level output containing all extracted findings from a radiology report."""

    exam_info: ExamInfo = Field(description="Metadata about the imaging exam")
    findings: list[ExtractedFinding] = Field(
        default_factory=list,
        description="All findings extracted from the report (present, absent, possible, indeterminate)",
    )
    non_finding_text: list[NonFindingText] = Field(
        default_factory=list,
        description="Report segments that don't contain clinical findings",
    )


class ValidationResult(StrictBaseModel):
    """Result of post-extraction validation.

    Contains warnings and errors detected during validation without blocking execution.
    The caller decides whether to retry or accept the extraction.
    """

    is_valid: bool = Field(description="Whether the extraction passed all critical checks")
    verbatim_errors: list[str] = Field(
        default_factory=list,
        description="Errors where report_text doesn't appear verbatim in the original report",
    )
    coverage_warnings: list[str] = Field(
        default_factory=list,
        description="Warnings about text segments that may have been skipped",
    )


class ExtractionUsage(StrictBaseModel):
    """Token and request usage captured from an extraction agent run."""

    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    duration_ms: int | None = None
    details: dict[str, int] = Field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionResult:
    """Return value from extract_findings() pairing output with usage."""

    extraction: ReportExtraction
    usage: ExtractionUsage | None


CodingMethod = Literal["exact", "synonym", "search", "agent", "unresolved"]


class AlternateCode(StrictBaseModel):
    """A candidate OIFM code from search results."""

    oifm_id: str
    name: str


class FindingCoding(StrictBaseModel):
    """OIFM coding result for a single extracted finding."""

    oifm_id: str | None = None
    oifm_name: str | None = None
    method: CodingMethod = "unresolved"
    alternates: list[AlternateCode] = Field(default_factory=list)


class LocationCoding(StrictBaseModel):
    """Anatomic location coding for a single extracted finding."""

    location_id: str | None = None
    location_name: str | None = None


class UnresolvedFinding(StrictBaseModel):
    """A finding that could not be mapped to an OIFM code."""

    finding_name: str
    finding_index: int


class CodingBridgeResult(StrictBaseModel):
    """Run-level output from the coding bridge."""

    finding_codings: list[FindingCoding]
    location_codings: list[LocationCoding]
    unresolved: list[UnresolvedFinding]
    coded_count: int
    unresolved_count: int


@dataclass
class ExtractorDeps:
    """Dependencies for the extraction agent — carries the original report text."""

    report_text: str
    status_callback: Callable[[str], Awaitable[None]] | None = field(default=None, repr=False)
