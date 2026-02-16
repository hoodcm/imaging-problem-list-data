"""Small adjudicator agents for ambiguous coding search results."""

from __future__ import annotations

import json
from typing import cast

from pydantic import Field
from pydantic_ai import Agent
from pydantic_ai.usage import UsageLimits

from finding_extractor.base import StrictBaseModel
from finding_extractor.config import get_settings
from finding_extractor.model_resilience import create_resilient_agent
from finding_extractor.models import AlternateCode


class CodingAdjudication(StrictBaseModel):
    """Output for finding or location candidate adjudication."""

    selected_id: str | None = Field(default=None)
    unresolved: bool = Field(default=False)
    rationale: str | None = Field(default=None)


def _instructions(scope: str) -> str:
    return (
        f"You are a radiology coding adjudicator for {scope}. "
        "Choose exactly one candidate id from the provided list when there is a plausible match. "
        "If no candidate is credible, set unresolved=true and selected_id=null. "
        "Never invent ids."
    )


def _create_agent(model_name: str, reasoning: str | None, scope: str) -> Agent[None, CodingAdjudication]:
    agent = create_resilient_agent(
        model_name=model_name,
        reasoning=reasoning,
        instructions=_instructions(scope),
        output_type=CodingAdjudication,
        output_retries=2,
    )
    return cast(Agent[None, CodingAdjudication], agent)


def _build_prompt(*, name: str, candidates: list[AlternateCode], context: str | None = None) -> str:
    payload = {
        "name": name,
        "context": context,
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
    }
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
) -> CodingAdjudication:
    """Resolve ambiguous finding coding candidates with a small LLM."""
    return await _adjudicate_candidates(
        scope="finding coding",
        name=finding_name,
        candidates=candidates,
        model_name=model_name,
        reasoning=reasoning,
    )


async def adjudicate_location_candidate(
    *,
    query: str,
    candidates: list[AlternateCode],
    model_name: str,
    reasoning: str | None,
) -> CodingAdjudication:
    """Resolve ambiguous location coding candidates with a small LLM."""
    return await _adjudicate_candidates(
        scope="anatomic location coding",
        name=query,
        candidates=candidates,
        model_name=model_name,
        reasoning=reasoning,
    )


def _validated_adjudication_output(
    output: CodingAdjudication,
    candidates: list[AlternateCode],
) -> CodingAdjudication:
    allowed = {candidate.oifm_id for candidate in candidates}
    if output.unresolved or output.selected_id is None or output.selected_id not in allowed:
        return CodingAdjudication(unresolved=True, rationale=output.rationale)
    return CodingAdjudication(selected_id=output.selected_id, unresolved=False, rationale=output.rationale)


async def _adjudicate_candidates(
    *,
    scope: str,
    name: str,
    candidates: list[AlternateCode],
    model_name: str,
    reasoning: str | None,
) -> CodingAdjudication:
    if not candidates:
        return CodingAdjudication(unresolved=True)

    agent = _create_agent(model_name, reasoning, scope=scope)
    usage_limits = UsageLimits(request_limit=min(4, get_settings().agent_request_limit))
    prompt = _build_prompt(name=name, candidates=candidates)
    result = await agent.run(prompt, usage_limits=usage_limits)
    return _validated_adjudication_output(result.output, candidates)
