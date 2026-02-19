"""Small adjudicator agents for ambiguous coding search results."""

from __future__ import annotations

import json
from typing import cast

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from finding_extractor.base import StrictBaseModel
from finding_extractor.model_resilience import create_resilient_agent
from finding_extractor.models import AlternateCode


class CodingAdjudication(StrictBaseModel):
    """Output for finding or location candidate adjudication."""

    selected_id: str | None = Field(default=None)
    unresolved: bool = Field(default=False)
    rationale: str | None = Field(default=None)
    suggested_canonical_name: str | None = Field(
        default=None,
        description="When unresolved, the canonical name the agent would have matched if a code existed.",
    )


def _instructions(scope: str) -> str:
    return (
        f"You are a radiology coding adjudicator for {scope}. "
        "Choose exactly one candidate id from the provided list when there is a plausible match. "
        "Rules:\n"
        "- The candidate must be anatomically compatible with the exam and finding context.\n"
        "- Prefer setting unresolved=true over selecting a weak or overly specific match.\n"
        "- Do not offer a more specific code than what the finding name describes.\n"
        "- When unresolved, set suggested_canonical_name to the best canonical term you would match.\n"
        "- If no candidate is credible, set unresolved=true and selected_id=null.\n"
        "- Never invent ids."
    )


def _create_agent(
    model_name: str, reasoning: str | None, scope: str
) -> Agent[None, CodingAdjudication]:
    agent = create_resilient_agent(
        model_name=model_name,
        reasoning=reasoning,
        instructions=_instructions(scope),
        output_type=CodingAdjudication,
        output_retries=2,
    )
    return cast(Agent[None, CodingAdjudication], agent)


def _build_prompt(
    *,
    name: str,
    candidates: list[AlternateCode],
    context: str | None = None,
    exam_modality: str | None = None,
    exam_body_part: str | None = None,
    exam_laterality: str | None = None,
    presence: str | None = None,
    location_body_region: str | None = None,
    location_specific_anatomy: str | None = None,
    location_laterality: str | None = None,
    evidence_text: str | None = None,
) -> str:
    payload: dict[str, object] = {"name": name}
    if context:
        payload["context"] = context

    # Exam context
    exam_context: dict[str, str] = {}
    if exam_modality:
        exam_context["modality"] = exam_modality
    if exam_body_part:
        exam_context["body_part"] = exam_body_part
    if exam_laterality:
        exam_context["laterality"] = exam_laterality
    if exam_context:
        payload["exam"] = exam_context

    # Finding context
    finding_context: dict[str, str] = {}
    if presence:
        finding_context["presence"] = presence
    if location_body_region:
        finding_context["body_region"] = location_body_region
    if location_specific_anatomy:
        finding_context["specific_anatomy"] = location_specific_anatomy
    if location_laterality:
        finding_context["laterality"] = location_laterality
    if finding_context:
        payload["finding_context"] = finding_context

    # Evidence (truncated for prompt efficiency)
    if evidence_text:
        truncated = evidence_text[:300]
        if len(evidence_text) > 300:
            truncated += "..."
        payload["evidence"] = truncated

    payload["candidates"] = [candidate.model_dump(mode="json") for candidate in candidates]

    return (
        "Select the best candidate id for this concept. "
        "If no candidate is reliable, set unresolved=true.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )


async def adjudicate_finding_candidate(
    *,
    finding_name: str,
    candidates: list[AlternateCode],
    model_name: str,
    reasoning: str | None,
    exam_modality: str | None = None,
    exam_body_part: str | None = None,
    exam_laterality: str | None = None,
    presence: str | None = None,
    location_body_region: str | None = None,
    location_specific_anatomy: str | None = None,
    location_laterality: str | None = None,
    evidence_text: str | None = None,
) -> CodingAdjudication:
    """Resolve ambiguous finding coding candidates with a small LLM."""
    return await _adjudicate_candidates(
        scope="finding coding",
        name=finding_name,
        candidates=candidates,
        model_name=model_name,
        reasoning=reasoning,
        exam_modality=exam_modality,
        exam_body_part=exam_body_part,
        exam_laterality=exam_laterality,
        presence=presence,
        location_body_region=location_body_region,
        location_specific_anatomy=location_specific_anatomy,
        location_laterality=location_laterality,
        evidence_text=evidence_text,
    )


async def adjudicate_location_candidate(
    *,
    query: str,
    candidates: list[AlternateCode],
    model_name: str,
    reasoning: str | None,
    exam_modality: str | None = None,
    exam_body_part: str | None = None,
    exam_laterality: str | None = None,
    presence: str | None = None,
    location_body_region: str | None = None,
    location_specific_anatomy: str | None = None,
    location_laterality: str | None = None,
    evidence_text: str | None = None,
) -> CodingAdjudication:
    """Resolve ambiguous location coding candidates with a small LLM."""
    return await _adjudicate_candidates(
        scope="anatomic location coding",
        name=query,
        candidates=candidates,
        model_name=model_name,
        reasoning=reasoning,
        exam_modality=exam_modality,
        exam_body_part=exam_body_part,
        exam_laterality=exam_laterality,
        presence=presence,
        location_body_region=location_body_region,
        location_specific_anatomy=location_specific_anatomy,
        location_laterality=location_laterality,
        evidence_text=evidence_text,
    )


def _validated_adjudication_output(
    output: CodingAdjudication,
    candidates: list[AlternateCode],
) -> CodingAdjudication:
    allowed = {candidate.oifm_id for candidate in candidates}
    if output.unresolved or output.selected_id is None or output.selected_id not in allowed:
        return CodingAdjudication(
            unresolved=True,
            rationale=output.rationale,
            suggested_canonical_name=output.suggested_canonical_name,
        )
    return CodingAdjudication(
        selected_id=output.selected_id,
        unresolved=False,
        rationale=output.rationale,
    )


async def _adjudicate_candidates(
    *,
    scope: str,
    name: str,
    candidates: list[AlternateCode],
    model_name: str,
    reasoning: str | None,
    exam_modality: str | None = None,
    exam_body_part: str | None = None,
    exam_laterality: str | None = None,
    presence: str | None = None,
    location_body_region: str | None = None,
    location_specific_anatomy: str | None = None,
    location_laterality: str | None = None,
    evidence_text: str | None = None,
) -> CodingAdjudication:
    if not candidates:
        return CodingAdjudication(unresolved=True)

    agent = _create_agent(model_name, reasoning, scope=scope)
    usage_limits = UsageLimits(request_limit=4)
    prompt = _build_prompt(
        name=name,
        candidates=candidates,
        exam_modality=exam_modality,
        exam_body_part=exam_body_part,
        exam_laterality=exam_laterality,
        presence=presence,
        location_body_region=location_body_region,
        location_specific_anatomy=location_specific_anatomy,
        location_laterality=location_laterality,
        evidence_text=evidence_text,
    )
    result = await agent.run(prompt, usage_limits=usage_limits)
    return _validated_adjudication_output(result.output, candidates)
