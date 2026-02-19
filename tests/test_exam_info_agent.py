"""Tests for the exam-info sub-agent module."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from finding_extractor.exam_info_agent import (
    ExamInfoExtraction,
    _build_exam_info_prompt,
    _to_exam_info,
    extract_exam_info,
)
from finding_extractor.models import ExamInfo


class TestExamInfoExtractionModel:
    def test_valid_full_extraction(self):
        result = ExamInfoExtraction(
            study_description="CT Abdomen and Pelvis WO contrast",
            modality="CT",
            body_part="abdomen",
            laterality=None,
        )
        assert result.modality == "CT"
        assert result.body_part == "abdomen"
        assert result.laterality is None

    def test_valid_with_laterality(self):
        result = ExamInfoExtraction(
            study_description="MR Left Shoulder",
            modality="MR",
            body_part="shoulder",
            laterality="left",
        )
        assert result.laterality == "left"

    def test_all_null_fields(self):
        result = ExamInfoExtraction()
        assert result.study_description is None
        assert result.modality is None
        assert result.body_part is None
        assert result.laterality is None


class TestBuildExamInfoPrompt:
    def test_prompt_includes_report_preview(self):
        prompt = _build_exam_info_prompt("Some report text here")
        assert "Some report text here" in prompt
        assert "Extract exam metadata" in prompt

    def test_prompt_includes_exam_description_hint(self):
        prompt = _build_exam_info_prompt(
            "Report text",
            exam_description="CT Abdomen",
        )
        assert "CT Abdomen" in prompt
        assert "exam_description_hint" in prompt

    def test_prompt_truncates_long_report(self):
        long_text = "A" * 1000
        prompt = _build_exam_info_prompt(long_text)
        assert "..." in prompt
        assert len(prompt) < 1000


class TestToExamInfo:
    def test_converts_full_extraction(self):
        extraction = ExamInfoExtraction(
            study_description="CT Abdomen",
            modality="CT",
            body_part="abdomen",
            laterality=None,
        )
        info = _to_exam_info(extraction, fallback_description="fallback")
        assert isinstance(info, ExamInfo)
        assert info.study_description == "CT Abdomen"
        assert info.modality == "CT"
        assert info.body_part == "abdomen"
        assert info.laterality is None

    def test_uses_fallback_when_description_empty(self):
        extraction = ExamInfoExtraction(
            study_description="",
            modality=None,
            body_part=None,
            laterality=None,
        )
        info = _to_exam_info(extraction, fallback_description="Radiology study")
        assert info.study_description == "Radiology study"

    def test_uses_fallback_when_description_none(self):
        extraction = ExamInfoExtraction()
        info = _to_exam_info(extraction, fallback_description="CT scan")
        assert info.study_description == "CT scan"

    def test_preserves_laterality(self):
        extraction = ExamInfoExtraction(
            study_description="MR Left Knee",
            modality="MR",
            body_part="knee",
            laterality="left",
        )
        info = _to_exam_info(extraction, fallback_description="fallback")
        assert info.laterality == "left"


@pytest.mark.asyncio
async def test_extract_exam_info_calls_agent(monkeypatch):
    """Verify the high-level function creates an agent and returns ExamInfo."""

    class _FakeAgent:
        async def run(self, _prompt, usage_limits=None):
            return SimpleNamespace(
                output=ExamInfoExtraction(
                    study_description="CT Abdomen and Pelvis",
                    modality="CT",
                    body_part="abdomen",
                    laterality=None,
                )
            )

    monkeypatch.setattr(
        "finding_extractor.exam_info_agent._create_exam_info_agent",
        lambda *_args, **_kwargs: _FakeAgent(),
    )

    info = await extract_exam_info(
        "Findings:\nNo acute findings.",
        exam_description="CT Abdomen",
        model_name="openai:gpt-5-mini",
        reasoning=None,
    )

    assert isinstance(info, ExamInfo)
    assert info.modality == "CT"
    assert info.body_part == "abdomen"
    assert info.study_description == "CT Abdomen and Pelvis"
