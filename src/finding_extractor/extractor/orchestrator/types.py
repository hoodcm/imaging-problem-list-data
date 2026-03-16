"""Types used by the chunk-scoped extraction orchestrator."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

from finding_extractor.models import (
    ExamInfo,
    ExtractedReportFindings,
    ExtractionResult,
    ExtractionUsage,
    PipelineDiagnostics,
    ValidationResult,
)

ExtractFindingsFn = Callable[..., Awaitable[ExtractionResult]]
ValidateExtractionFn = Callable[[str, ExtractedReportFindings], ValidationResult]
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



@dataclass(frozen=True)
class ChunkPipelineResult:
    """Result of one chunk's full pipeline: extract → review → correction."""

    outcome: ChunkExtractionOutcome
    decision: ExtractionReviewDecision | None
    was_reextracted: bool = False
