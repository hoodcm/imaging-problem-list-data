"""Unit tests for validator-guided extraction review helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from finding_extractor.extraction_orchestrator import SectionExtractionUnit
from finding_extractor.extraction_review import ReviewOutput, ReviewRequest, review_extraction_units
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
            requests=[
                ReviewRequest(unit_label="impression_1", feedback="check for missed findings"),
                ReviewRequest(unit_label="bogus", feedback="invalid"),
                ReviewRequest(unit_label="impression_1", feedback="duplicate"),
                ReviewRequest(unit_label="findings_1", feedback="recheck presence"),
            ],
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
    assert len(decision.reextract_requests) == 2
    assert decision.reextract_requests[0].label == "impression_1"
    assert decision.reextract_requests[0].feedback == "check for missed findings"
    assert decision.reextract_requests[1].label == "findings_1"
    assert decision.reextract_requests[1].feedback == "recheck presence"


@pytest.mark.asyncio
async def test_review_extraction_units_ignores_labels_when_should_reextract_false(monkeypatch):
    fake_agent = _FakeReviewAgent(
        ReviewOutput(
            should_reextract=False,
            requests=[
                ReviewRequest(unit_label="findings_1"),
            ],
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
    assert decision.reextract_requests == ()
    assert decision.rationale == "looks fine"


class TestReviewRequestModel:
    def test_review_request_with_feedback(self):
        req = ReviewRequest(
            unit_label="findings_1",
            feedback="Look for hepatic findings",
            suspected_issue="missed finding",
        )
        assert req.unit_label == "findings_1"
        assert req.feedback == "Look for hepatic findings"
        assert req.suspected_issue == "missed finding"

    def test_review_request_defaults(self):
        req = ReviewRequest(unit_label="findings_1")
        assert req.feedback == ""
        assert req.suspected_issue == ""


class TestReviewOutputModel:
    def test_review_output_with_requests(self):
        output = ReviewOutput(
            should_reextract=True,
            requests=[
                ReviewRequest(unit_label="findings_1", feedback="check for missed findings"),
            ],
            rationale="missed detail",
        )
        assert output.should_reextract is True
        assert len(output.requests) == 1
        assert output.requests[0].unit_label == "findings_1"

    def test_review_output_defaults(self):
        output = ReviewOutput()
        assert output.should_reextract is False
        assert output.requests == []
        assert output.rationale is None
