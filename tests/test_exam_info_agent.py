"""Tests for the exam-info sub-agent module."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from finding_extractor.extractor.exam_info_agent import (
    ExamInfoExtraction,
    _build_exam_info_prompt,
    _to_exam_info,
    extract_exam_info,
)
from finding_extractor.models import ExamInfo


class TestExamInfoExtractionModel:
    def test_valid_full_extraction(self):
        result = ExamInfoExtraction(
            study_description="CT Abdomen and Pelvis With IV Contrast",
            modality="CT",
            body_region="abdomen",
            body_part="abdomen, pelvis",
            contrast="with",
            laterality=None,
        )
        assert result.modality == "CT"
        assert result.body_region == "abdomen"
        assert result.body_part == "abdomen, pelvis"
        assert result.contrast == "with"
        assert result.laterality is None

    def test_valid_with_laterality(self):
        result = ExamInfoExtraction(
            study_description="XR Left Shoulder",
            modality="XR",
            body_region="upper extremity",
            body_part="shoulder",
            contrast=None,
            laterality="left",
        )
        assert result.laterality == "left"
        assert result.body_region == "upper extremity"

    def test_all_null_fields(self):
        result = ExamInfoExtraction()
        assert result.study_description is None
        assert result.modality is None
        assert result.body_region is None
        assert result.body_part is None
        assert result.contrast is None
        assert result.laterality is None

    def test_valid_modality_codes(self):
        for code in ("CT", "XR", "MR", "US", "NM", "PET", "FLUORO", "MG", "DXA", "IR"):
            result = ExamInfoExtraction(modality=code)
            assert result.modality == code

    def test_invalid_modality_rejected(self):
        with pytest.raises(ValidationError):
            ExamInfoExtraction.model_validate({"modality": "INVALID"})

    def test_valid_body_regions(self):
        for region in (
            "chest", "abdomen", "pelvis", "head", "neck",
            "spine", "upper extremity", "lower extremity", "breast",
        ):
            result = ExamInfoExtraction(body_region=region)
            assert result.body_region == region

    def test_invalid_body_region_rejected(self):
        with pytest.raises(ValidationError):
            ExamInfoExtraction.model_validate({"body_region": "torso"})

    def test_valid_contrast_values(self):
        for val in ("with", "without", "without and with"):
            result = ExamInfoExtraction(contrast=val)
            assert result.contrast == val

    def test_invalid_contrast_rejected(self):
        with pytest.raises(ValidationError):
            ExamInfoExtraction.model_validate({"contrast": "oral"})

    def test_body_part_unconstrained(self):
        """body_part accepts any string — it's not constrained."""
        for term in ("brain", "shoulder", "abdomen, pelvis", "left kidney", "thoracolumbar spine"):
            result = ExamInfoExtraction(body_part=term)
            assert result.body_part == term

    def test_dual_phase_contrast(self):
        result = ExamInfoExtraction(
            study_description="MR Brain Without and With Contrast",
            modality="MR",
            body_region="head",
            body_part="brain",
            contrast="without and with",
        )
        assert result.contrast == "without and with"


class TestBuildExamInfoPrompt:
    def test_prompt_includes_report_context_first_20_lines(self):
        lines = [f"Line {i}" for i in range(30)]
        report_text = "\n".join(lines)
        prompt = _build_exam_info_prompt(report_text)
        assert "Line 0" in prompt
        assert "Line 19" in prompt
        assert "Line 20" not in prompt
        assert "report_context" in prompt

    def test_prompt_includes_exam_description_hint(self):
        prompt = _build_exam_info_prompt(
            "Report text",
            exam_description="CT Abdomen",
        )
        assert "CT Abdomen" in prompt
        assert "exam_description_hint" in prompt

    def test_prompt_includes_source_ref_and_external_metadata(self):
        prompt = _build_exam_info_prompt(
            "Report text",
            source_ref="sample_data/example2/ct_abdomen_20230118.md",
            external_metadata={"report_id": "abc-123"},
        )
        assert "sample_data/example2/ct_abdomen_20230118.md" in prompt
        assert "external_metadata" in prompt
        assert "abc-123" in prompt

    def test_prompt_short_report_included_fully(self):
        short_text = "Short report\nwith two lines"
        prompt = _build_exam_info_prompt(short_text)
        assert "Short report" in prompt
        assert "with two lines" in prompt

    def test_prompt_no_report_headers_key(self):
        """report_headers parameter was removed — prompt should not contain it."""
        prompt = _build_exam_info_prompt("Report text")
        assert "report_headers" not in prompt
        assert "report_preview" not in prompt


class TestToExamInfo:
    def test_converts_full_extraction(self):
        extraction = ExamInfoExtraction(
            study_description="CT Abdomen and Pelvis With IV Contrast",
            modality="CT",
            body_region="abdomen",
            body_part="abdomen, pelvis",
            contrast="with",
            laterality=None,
        )
        info = _to_exam_info(extraction, fallback_description="fallback")
        assert isinstance(info, ExamInfo)
        assert info.study_description == "CT Abdomen and Pelvis With IV Contrast"
        assert info.modality == "CT"
        assert info.body_region == "abdomen"
        assert info.body_part == "abdomen, pelvis"
        assert info.contrast == "with"
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
            study_description="XR Left Shoulder",
            modality="XR",
            body_region="upper extremity",
            body_part="shoulder",
            laterality="left",
        )
        info = _to_exam_info(extraction, fallback_description="fallback")
        assert info.laterality == "left"
        assert info.body_region == "upper extremity"

    def test_maps_body_region_and_contrast(self):
        extraction = ExamInfoExtraction(
            study_description="MR Brain Without and With Contrast",
            modality="MR",
            body_region="head",
            body_part="brain",
            contrast="without and with",
        )
        info = _to_exam_info(extraction, fallback_description="fallback")
        assert info.body_region == "head"
        assert info.contrast == "without and with"

    def test_modality_not_uppercased(self):
        """Modality is now a Literal — no .upper() transformation needed."""
        extraction = ExamInfoExtraction(modality="CT")
        info = _to_exam_info(extraction, fallback_description="fallback")
        assert info.modality == "CT"


@pytest.mark.asyncio
async def test_extract_exam_info_calls_agent(monkeypatch):
    """Verify the high-level function creates an agent and returns ExamInfo."""

    class _FakeAgent:
        async def run(self, _prompt, usage_limits=None):
            return SimpleNamespace(
                output=ExamInfoExtraction(
                    study_description="CT Abdomen and Pelvis With IV Contrast",
                    modality="CT",
                    body_region="abdomen",
                    body_part="abdomen, pelvis",
                    contrast="with",
                    laterality=None,
                )
            )

    monkeypatch.setattr(
        "finding_extractor.extractor.exam_info_agent._create_exam_info_agent",
        lambda *_args, **_kwargs: _FakeAgent(),
    )

    info = await extract_exam_info(
        "Findings:\nNo acute findings.",
        exam_description="CT Abdomen",
        source_ref="sample_data/example2/ct_abdomen_20230118.md",
        external_metadata={"report_id": "r-1"},
        model_name="openai:gpt-5-mini",
        reasoning=None,
    )

    assert isinstance(info, ExamInfo)
    assert info.modality == "CT"
    assert info.body_region == "abdomen"
    assert info.body_part == "abdomen, pelvis"
    assert info.contrast == "with"
    assert info.study_description == "CT Abdomen and Pelvis With IV Contrast"
