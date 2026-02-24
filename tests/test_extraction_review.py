"""Unit tests for single-chunk validator review helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from finding_extractor.extraction_orchestrator import ExtractionReviewDecision
from finding_extractor.extraction_review import (
    ReviewOutput,
    ReviewProblemOutput,
    review_extraction_chunk,
)
from finding_extractor.models import ExamInfo, ExtractedFinding, FindingLocation, ReportExtraction


class _FakeReviewAgent:
    def __init__(self, output: ReviewOutput):
        self._output = output

    async def run(self, _prompt: str, usage_limits=None):
        return SimpleNamespace(output=self._output, usage_limits=usage_limits)


def _sample_chunk_extraction() -> ReportExtraction:
    return ReportExtraction(
        exam_info=ExamInfo(study_description="CT Abdomen"),
        findings=[
            ExtractedFinding(
                finding_name="renal_stone",
                presence="present",
                location=FindingLocation(body_region="abdomen", specific_anatomy="right kidney"),
                report_text="3 mm nonobstructive right renal stone.",
                source_section="findings",
            )
        ],
        non_finding_text=[],
    )


@pytest.mark.asyncio
async def test_review_extraction_chunk_returns_reextract_decision_with_valid_problem(monkeypatch):
    fake_agent = _FakeReviewAgent(
        ReviewOutput(
            report_chunk_id="findings_1",
            should_reextract=True,
            problems=[
                ReviewProblemOutput(
                    raw_extracted_finding_index=0,
                    extract_problem_type="wrong_presence",
                    problem_detail="Text indicates possible, not present.",
                )
            ],
            rationale="presence mismatch",
        )
    )
    monkeypatch.setattr(
        "finding_extractor.extraction_review._create_review_agent",
        lambda *_args, **_kwargs: fake_agent,
    )

    decision = await review_extraction_chunk(
        report_chunk_id="findings_1",
        section_name="findings",
        report_chunk="3 mm nonobstructive right renal stone.",
        preceding_chunk_context=None,
        following_chunk_context=None,
        chunk_extraction=_sample_chunk_extraction(),
        exam_info=ExamInfo(study_description="CT Abdomen", modality="CT", body_part="abdomen"),
        model_name="openai:gpt-5-mini",
        reasoning="minimal",
    )

    assert decision == ExtractionReviewDecision(
        report_chunk_id="findings_1",
        should_reextract=True,
        problems=decision.problems,
        rationale="presence mismatch",
    )
    assert len(decision.problems) == 1
    assert decision.problems[0].raw_extracted_finding_index == 0
    assert decision.problems[0].extract_problem_type == "wrong_presence"


@pytest.mark.asyncio
async def test_review_extraction_chunk_mismatched_chunk_id_is_safely_ignored(monkeypatch):
    fake_agent = _FakeReviewAgent(
        ReviewOutput(
            report_chunk_id="wrong_id",
            should_reextract=True,
            problems=[
                ReviewProblemOutput(
                    raw_extracted_finding_index=0,
                    extract_problem_type="hallucination",
                    problem_detail="unsupported",
                )
            ],
        )
    )
    monkeypatch.setattr(
        "finding_extractor.extraction_review._create_review_agent",
        lambda *_args, **_kwargs: fake_agent,
    )

    decision = await review_extraction_chunk(
        report_chunk_id="findings_1",
        section_name="findings",
        report_chunk="3 mm nonobstructive right renal stone.",
        preceding_chunk_context=None,
        following_chunk_context=None,
        chunk_extraction=_sample_chunk_extraction(),
        exam_info=ExamInfo(study_description="CT Abdomen"),
        model_name="openai:gpt-5-mini",
        reasoning="minimal",
    )

    assert decision.should_reextract is False
    assert decision.report_chunk_id == "findings_1"
    assert decision.problems == ()


@pytest.mark.asyncio
async def test_review_extraction_chunk_filters_out_of_range_problem_indexes(monkeypatch):
    fake_agent = _FakeReviewAgent(
        ReviewOutput(
            report_chunk_id="findings_1",
            should_reextract=True,
            problems=[
                ReviewProblemOutput(
                    raw_extracted_finding_index=99,
                    extract_problem_type="wrong_presence",
                    problem_detail="bad index",
                )
            ],
            rationale="index invalid",
        )
    )
    monkeypatch.setattr(
        "finding_extractor.extraction_review._create_review_agent",
        lambda *_args, **_kwargs: fake_agent,
    )

    decision = await review_extraction_chunk(
        report_chunk_id="findings_1",
        section_name="findings",
        report_chunk="3 mm nonobstructive right renal stone.",
        preceding_chunk_context=None,
        following_chunk_context=None,
        chunk_extraction=_sample_chunk_extraction(),
        exam_info=ExamInfo(study_description="CT Abdomen"),
        model_name="openai:gpt-5-mini",
        reasoning="minimal",
    )

    assert decision.should_reextract is False
    assert decision.problems == ()


@pytest.mark.asyncio
async def test_review_extraction_chunk_clears_problems_when_should_reextract_false(monkeypatch):
    fake_agent = _FakeReviewAgent(
        ReviewOutput(
            report_chunk_id="findings_1",
            should_reextract=False,
            problems=[
                ReviewProblemOutput(
                    raw_extracted_finding_index=0,
                    extract_problem_type="wrong_presence",
                    problem_detail="should be dropped",
                )
            ],
            rationale="looks fine",
        )
    )
    monkeypatch.setattr(
        "finding_extractor.extraction_review._create_review_agent",
        lambda *_args, **_kwargs: fake_agent,
    )

    decision = await review_extraction_chunk(
        report_chunk_id="findings_1",
        section_name="findings",
        report_chunk="3 mm nonobstructive right renal stone.",
        preceding_chunk_context=None,
        following_chunk_context=None,
        chunk_extraction=_sample_chunk_extraction(),
        exam_info=ExamInfo(study_description="CT Abdomen"),
        model_name="openai:gpt-5-mini",
        reasoning="minimal",
    )

    assert decision.should_reextract is False
    assert decision.problems == ()
    assert decision.rationale == "looks fine"
