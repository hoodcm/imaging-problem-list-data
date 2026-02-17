"""Unit tests for coding adjudicator agent helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic_ai.usage import UsageLimits

from finding_extractor.coding_agents import (
    CodingAdjudication,
    adjudicate_finding_candidate,
    adjudicate_location_candidate,
)
from finding_extractor.models import AlternateCode


class _FakeAgent:
    def __init__(self, output: CodingAdjudication):
        self._output = output
        self.calls: list[tuple[str, UsageLimits | None]] = []

    async def run(self, prompt: str, usage_limits=None):
        self.calls.append((prompt, usage_limits))
        return SimpleNamespace(output=self._output)


@pytest.mark.asyncio
async def test_adjudicate_finding_candidate_returns_unresolved_for_empty_candidates(monkeypatch):
    monkeypatch.setattr(
        "finding_extractor.coding_agents._create_agent",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    result = await adjudicate_finding_candidate(
        finding_name="renal stone",
        candidates=[],
        model_name="openai:gpt-5-mini",
        reasoning="none",
    )

    assert result.unresolved is True
    assert result.selected_id is None


@pytest.mark.asyncio
async def test_adjudicate_finding_candidate_accepts_allowlisted_id(monkeypatch):
    fake_agent = _FakeAgent(CodingAdjudication(selected_id="OIFM_1", unresolved=False))
    monkeypatch.setattr(
        "finding_extractor.coding_agents._create_agent",
        lambda *_args, **_kwargs: fake_agent,
    )
    candidates = [
        AlternateCode(oifm_id="OIFM_1", name="urinary tract calculus"),
        AlternateCode(oifm_id="OIFM_2", name="nephrolithiasis"),
    ]

    result = await adjudicate_finding_candidate(
        finding_name="kidney stone",
        candidates=candidates,
        model_name="openai:gpt-5-mini",
        reasoning="none",
    )

    assert result.unresolved is False
    assert result.selected_id == "OIFM_1"
    assert len(fake_agent.calls) == 1
    _prompt, usage_limits = fake_agent.calls[0]
    assert usage_limits is not None
    assert usage_limits.request_limit == 4


@pytest.mark.asyncio
async def test_adjudicate_location_candidate_rejects_non_allowlisted_id(monkeypatch):
    fake_agent = _FakeAgent(CodingAdjudication(selected_id="RID999", unresolved=False, rationale="bad id"))
    monkeypatch.setattr(
        "finding_extractor.coding_agents._create_agent",
        lambda *_args, **_kwargs: fake_agent,
    )
    candidates = [
        AlternateCode(oifm_id="RID1", name="left kidney"),
        AlternateCode(oifm_id="RID2", name="right kidney"),
    ]

    result = await adjudicate_location_candidate(
        query="kidney",
        candidates=candidates,
        model_name="openai:gpt-5-mini",
        reasoning="none",
    )

    assert result.unresolved is True
    assert result.selected_id is None
    assert result.rationale == "bad id"
