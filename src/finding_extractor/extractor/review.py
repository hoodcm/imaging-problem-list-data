"""LLM review pass for single-chunk extraction review decisions."""

from __future__ import annotations

from typing import cast

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from finding_extractor.core.base_model import StrictBaseModel
from finding_extractor.core.config import get_settings
from finding_extractor.extractor.orchestrator.types import (
    ExtractionReviewDecision,
    ExtractionReviewProblem,
    ExtractProblemType,
)
from finding_extractor.llm.resilience import create_resilient_agent
from finding_extractor.models import ExamInfo, ExtractedReportFindings

EXTRACTION_TASK_SUMMARY = """EXTRACTION_TASK_SUMMARY
- Evaluate extraction quality for this report_chunk; do not perform a fresh extraction.
- Evidence boundary: only REPORT_CHUNK is evidence; surrounding context is advisory.
- Check that ALL clinically meaningful findings in REPORT_CHUNK are represented, and that EACH extracted finding is supported by REPORT_CHUNK.
- Presence labels must match text intent: present, absent, possible, indeterminate.
- Explicit negatives should be represented as clinically meaningful absent findings; blanket negatives should map to appropriately scoped absent findings (e.g., "clear lungs" -> {"finding_name": "pulmonary parenchymal abnormality", "presence": "absent"}), not unrelated or over-specific absent findings.
- Finding and location names should use STANDARD terminology (not raw report phrasing), and should not be more specific than the chunk supports.
- Location fields should be clinically plausible and text-supported (or clearly inferable).
- Verbatim evidence requirement applies: extracted evidence must be exact chunk text, not paraphrase."""


class ReviewProblemOutput(StrictBaseModel):
    """One validator-identified problem for a reviewed chunk."""

    raw_extracted_finding_index: int | None = None
    extract_problem_type: ExtractProblemType
    problem_detail: str = Field(min_length=1)


class ReviewOutput(StrictBaseModel):
    """Single-chunk validator review decision output."""

    report_chunk_id: str
    should_reextract: bool = False
    problems: list[ReviewProblemOutput] = Field(default_factory=list)
    rationale: str | None = None


def _format_findings_table(extraction: ExtractedReportFindings) -> str:
    lines = [
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


def _build_review_prompt(
    *,
    report_chunk_id: str,
    section_name: str,
    chunk_text: str,
    preceding_chunk_context: str | None,
    following_chunk_context: str | None,
    chunk_extraction: ExtractedReportFindings,
    exam_info: ExamInfo,
) -> str:
    return (
        "Review chunk-level finding representation quality.\n"
        "For each structured data extraction, compare target chunk text and extracted findings.\n\n"
        f"{EXTRACTION_TASK_SUMMARY}\n\n"
        f"REPORT_CHUNK_ID\n{report_chunk_id}\n\n"
        "EXAM_INFO\n"
        f"- study_description: {exam_info.study_description}\n"
        f"- modality: {exam_info.modality or '(unknown)'}\n"
        f"- body_region: {exam_info.body_region or '(unknown)'}\n"
        f"- body_part: {exam_info.body_part or '(unknown)'}\n"
        f"- contrast: {exam_info.contrast or '(unknown)'}\n\n"
        f"SECTION\n{section_name}\n\n"
        "PRECEDING_CHUNK_CONTEXT\n"
        f"{preceding_chunk_context or '(none)'}\n\n"
        "REPORT_CHUNK\n"
        f"{chunk_text}\n\n"
        "FOLLOWING_CHUNK_CONTEXT\n"
        f"{following_chunk_context or '(none)'}\n\n"
        "CHUNK_EXTRACTION\n"
        f"{_format_findings_table(chunk_extraction)}"
    )


def _review_instructions() -> str:
    return (
        "You are a diligent radiology informatics assistant who carefully reviews the results of\n"
        "extracting data structures representing imaging findings from chunks of unstructured radiology\n"
        "report text.\n\n"
        "Your goal is to determine whether the data structures provide an accurate representation of\n"
        "natural language in the radiology report or if the extraction should be re-run with clarifying\n"
        "instructions.\n\n"
        "Issue patterns that justify re-extraction:\n"
        "- extraction structure contains clinically meaningful content unsupported by the chunk text (hallucination)\n"
        "- some report text describing a finding is not represented by any extraction data structure (missed finding)\n"
        "- a structure describes a finding as being present when it is not, or absent when it is possible (wrong presence)\n"
        "- finding name is more specific than described in the chunk text (too specific finding name)\n"
        "- incorrect representation of a blanket negative (incorrect blanket negative)\n"
        "- wrong or too-specific or general location information (incorrect location)\n\n"
        "Do not request re-extraction for formatting/style differences alone.\n\n"
        "Return one decision object for the provided report_chunk_id with fields:\n"
        "- report_chunk_id\n"
        "- should_reextract\n"
        "- problems[] where each item has raw_extracted_finding_index, extract_problem_type, problem_detail\n"
        "- rationale\n"
        "If should_reextract is false, return problems as an empty list."
    )


def _create_review_agent(model_name: str, reasoning: str | None) -> Agent[None, ReviewOutput]:
    agent = create_resilient_agent(
        model_name=model_name,
        reasoning=reasoning,
        instructions=_review_instructions(),
        output_type=ReviewOutput,
        output_retries=2,
    )
    return cast(Agent[None, ReviewOutput], agent)


def _normalize_review_output(
    *,
    output: ReviewOutput,
    expected_report_chunk_id: str,
    findings_count: int,
) -> ExtractionReviewDecision:
    if output.report_chunk_id != expected_report_chunk_id:
        return ExtractionReviewDecision(
            report_chunk_id=expected_report_chunk_id,
            should_reextract=False,
            rationale=(
                "Validator returned mismatched report_chunk_id; skipping re-extraction for safety."
            ),
        )

    problems: list[ExtractionReviewProblem] = []
    for problem in output.problems:
        detail = problem.problem_detail.strip()
        if not detail:
            continue
        idx = problem.raw_extracted_finding_index
        if idx is not None and (idx < 0 or idx >= findings_count):
            continue
        problems.append(
            ExtractionReviewProblem(
                raw_extracted_finding_index=idx,
                extract_problem_type=problem.extract_problem_type,
                problem_detail=detail,
            )
        )

    if not output.should_reextract:
        return ExtractionReviewDecision(
            report_chunk_id=expected_report_chunk_id,
            should_reextract=False,
            problems=(),
            rationale=output.rationale,
        )

    if not problems:
        return ExtractionReviewDecision(
            report_chunk_id=expected_report_chunk_id,
            should_reextract=False,
            problems=(),
            rationale=(
                output.rationale
                or "Validator requested re-extraction without valid problems; skipping re-extraction."
            ),
        )

    return ExtractionReviewDecision(
        report_chunk_id=expected_report_chunk_id,
        should_reextract=True,
        problems=tuple(problems),
        rationale=output.rationale,
    )


async def review_extraction_chunk(
    *,
    report_chunk_id: str,
    section_name: str,
    chunk_text: str,
    preceding_chunk_context: str | None,
    following_chunk_context: str | None,
    chunk_extraction: ExtractedReportFindings,
    exam_info: ExamInfo,
    model_name: str | None = None,
    reasoning: str | None = None,
) -> ExtractionReviewDecision:
    """Review one chunk extraction and decide whether that chunk needs re-extraction."""
    settings = get_settings()
    effective_model = model_name or settings.default_model
    agent = _create_review_agent(effective_model, reasoning)
    prompt = _build_review_prompt(
        report_chunk_id=report_chunk_id,
        section_name=section_name,
        chunk_text=chunk_text,
        preceding_chunk_context=preceding_chunk_context,
        following_chunk_context=following_chunk_context,
        chunk_extraction=chunk_extraction,
        exam_info=exam_info,
    )
    usage_limits = UsageLimits(request_limit=6)

    result = await agent.run(prompt, usage_limits=usage_limits)
    output = result.output

    return _normalize_review_output(
        output=output,
        expected_report_chunk_id=report_chunk_id,
        findings_count=len(chunk_extraction.findings),
    )
