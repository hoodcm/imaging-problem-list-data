"""Unit tests for validator-guided extraction review helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from finding_extractor.extraction_orchestrator import SectionExtractionUnit
from finding_extractor.extraction_review import ReviewOutput, review_extraction_units
from finding_extractor.models import ExamInfo, ExtractedFinding, ReportExtraction


class _FakeReviewAgent:
    def __init__(self, output: ReviewOutput):
        self._output = output

    async def run(self, _prompt: str, usage_limits=None):
        return SimpleNamespace(output=self._output, usage_limits=usage_limits)


def _sample_extraction() -> ReportExtraction:
    return ReportExtraction(
        exam_info=ExamInfo(study_description="CT Abdomen"),
        findings=[
            ExtractedFinding(
                finding_name="renal_stone",
                presence="present",
                report_text="3 mm nonobstructive right renal stone.",
                source_section="findings",
            )
        ],
        non_finding_text=[],
    )


def _sample_units() -> tuple[SectionExtractionUnit, ...]:
    return (
        SectionExtractionUnit(
            index=0,
            section_name="findings",
            label="findings_1",
            report_text="3 mm nonobstructive right renal stone.",
            prev_context_text=None,
            next_context_text=None,
        ),
        SectionExtractionUnit(
            index=1,
            section_name="impression",
            label="impression_1",
            report_text="Nonobstructive right nephrolithiasis.",
            prev_context_text=None,
            next_context_text=None,
        ),
    )


@pytest.mark.asyncio
async def test_review_extraction_units_filters_to_allowlisted_unique_labels(monkeypatch):
    fake_agent = _FakeReviewAgent(
        ReviewOutput(
            should_reextract=True,
            unit_labels=["impression_1", "bogus", "impression_1", "findings_1"],
            rationale="possible missed detail",
        )
    )
    monkeypatch.setattr(
        "finding_extractor.extraction_review._create_review_agent",
        lambda *_args, **_kwargs: fake_agent,
    )

    decision = await review_extraction_units(
        report_text="Findings and impression text",
        extraction=_sample_extraction(),
        units=_sample_units(),
        model_name="openai:gpt-5-mini",
        reasoning="minimal",
    )

    assert decision.reextract_unit_labels == ("impression_1", "findings_1")
    assert decision.rationale == "possible missed detail"


@pytest.mark.asyncio
async def test_review_extraction_units_ignores_labels_when_should_reextract_false(monkeypatch):
    fake_agent = _FakeReviewAgent(
        ReviewOutput(
            should_reextract=False,
            unit_labels=["findings_1"],
            rationale="looks fine",
        )
    )
    monkeypatch.setattr(
        "finding_extractor.extraction_review._create_review_agent",
        lambda *_args, **_kwargs: fake_agent,
    )

    decision = await review_extraction_units(
        report_text="Findings and impression text",
        extraction=_sample_extraction(),
        units=_sample_units(),
        model_name="openai:gpt-5-mini",
        reasoning="minimal",
    )

    assert decision.reextract_unit_labels == ()
    assert decision.rationale == "looks fine"
