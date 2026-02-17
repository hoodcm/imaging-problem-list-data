"""LLM review pass for targeted chunk re-extraction decisions."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import cast

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from finding_extractor.base import StrictBaseModel
from finding_extractor.config import get_settings
from finding_extractor.extraction_orchestrator import (
    SectionExtractionUnit,
    ValidationReviewDecision,
)
from finding_extractor.model_resilience import create_resilient_agent
from finding_extractor.models import ReportExtraction


class ReviewOutput(StrictBaseModel):
    """Structured review response for targeted re-extraction."""

    should_reextract: bool = False
    unit_labels: list[str] = Field(default_factory=list)
    rationale: str | None = None


@dataclass(frozen=True)
class UnitSummary:
    """Compact summary supplied to the review model for each extraction unit."""

    label: str
    section_name: str
    target_preview: str
    has_prev_context: bool
    has_next_context: bool


@dataclass(frozen=True)
class FindingSummary:
    """Compact summary supplied to the review model for extracted findings."""

    finding_name: str
    presence: str
    source_section: str | None
    evidence_preview: str


def _preview(text: str, limit: int = 180) -> str:
    cleaned = " ".join(text.split())
    if len(cleaned) <= limit:
        return cleaned
    return cleaned[: limit - 3].rstrip() + "..."


def _build_review_prompt(
    *,
    report_text: str,
    extraction: ReportExtraction,
    units: tuple[SectionExtractionUnit, ...],
) -> str:
    unit_summaries = [
        UnitSummary(
            label=unit.label,
            section_name=unit.section_name,
            target_preview=_preview(unit.report_text),
            has_prev_context=bool(unit.prev_context_text),
            has_next_context=bool(unit.next_context_text),
        )
        for unit in units
    ]
    finding_summaries = [
        FindingSummary(
            finding_name=finding.finding_name,
            presence=finding.presence,
            source_section=finding.source_section,
            evidence_preview=_preview(finding.report_text),
        )
        for finding in extraction.findings
    ]

    payload = {
        "report_preview": _preview(report_text, limit=360),
        "unit_summaries": [asdict(unit) for unit in unit_summaries],
        "finding_summaries": [asdict(finding) for finding in finding_summaries],
    }

    return (
        "Review this extraction for probable missed or inconsistent chunk coverage. "
        "If re-extraction is needed, return only unit labels from the provided list. "
        "Do not invent labels. Keep re-extraction set minimal.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


def _review_instructions() -> str:
    return (
        "You are a strict extraction quality reviewer. "
        "Only request re-extraction when there is strong evidence that a chunk may have "
        "missed clinically relevant finding content or has inconsistent extraction evidence. "
        "Prefer precision over recall: avoid unnecessary reruns."
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


async def review_extraction_units(
    *,
    report_text: str,
    extraction: ReportExtraction,
    units: tuple[SectionExtractionUnit, ...],
    model_name: str | None = None,
    reasoning: str | None = None,
) -> ValidationReviewDecision:
    """Ask an LLM reviewer whether targeted chunk re-extraction is needed."""
    settings = get_settings()
    effective_model = model_name or settings.default_model
    agent = _create_review_agent(effective_model, reasoning)
    prompt = _build_review_prompt(report_text=report_text, extraction=extraction, units=units)
    usage_limits = UsageLimits(request_limit=6)

    result = await agent.run(prompt, usage_limits=usage_limits)
    output = result.output

    labels: list[str] = []
    if output.should_reextract:
        allowed = {unit.label for unit in units}
        for label in output.unit_labels:
            if label in allowed and label not in labels:
                labels.append(label)

    return ValidationReviewDecision(
        reextract_unit_labels=tuple(labels),
        rationale=output.rationale,
    )
