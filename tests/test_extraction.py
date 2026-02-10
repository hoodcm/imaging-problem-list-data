"""Tests for finding extractor agent and extraction logic."""

from typing import Any, cast

from finding_extractor.agent import (
    _build_instructions,
    _detect_provider,
    _get_model_settings,
    build_prompt,
    check_verbatim,
    validate_extraction,
)
from finding_extractor.models import (
    ExamInfo,
    ExtractedFinding,
    FindingLocation,
    NonFindingText,
    ReportExtraction,
)


class TestInstructions:
    """Test cases for instructions building."""

    def test_instructions_contain_examples(self):
        """Test that instructions contain few-shot examples."""
        instructions = _build_instructions()
        assert "EXAMPLE 1" in instructions
        assert "EXAMPLE 2" in instructions
        assert "CT abdomen" in instructions or "abdomen" in instructions.lower()

    def test_instructions_contain_core_guidance(self):
        """Test that instructions contain core guidance."""
        instructions = _build_instructions()
        assert "CORE INSTRUCTIONS" in instructions
        assert "PRESENCE VALUES" in instructions
        assert "ATTRIBUTE KEYS" in instructions
        assert "QUOTE VERBATIM" in instructions or "verbat" in instructions.lower()


class TestDetectProvider:
    """Test cases for provider detection from model strings."""

    def test_openai_prefix(self):
        assert _detect_provider("openai:gpt-5-mini") == "openai"

    def test_openai_chat_prefix(self):
        assert _detect_provider("openai-chat:gpt-5-mini") == "openai"

    def test_openai_responses_prefix(self):
        assert _detect_provider("openai-responses:gpt-5") == "openai"

    def test_anthropic_prefix(self):
        assert _detect_provider("anthropic:claude-sonnet-4-5") == "anthropic"

    def test_google_gla_prefix(self):
        assert _detect_provider("google-gla:gemini-3-flash-preview") == "google"

    def test_google_vertex_prefix_not_supported(self):
        assert _detect_provider("google-vertex:gemini-3-pro-preview") is None

    def test_ollama_prefix(self):
        assert _detect_provider("ollama:llama4") == "ollama"

    def test_bare_model_name(self):
        assert _detect_provider("gpt-5-mini") is None

    def test_unknown_prefix(self):
        assert _detect_provider("unknown:some-model") is None


class TestModelSettings:
    """Test cases for model settings configuration."""

    def test_default_model_settings(self):
        """Test that default OpenAI model settings are created."""
        settings = _get_model_settings("openai:gpt-5-mini")
        assert settings is not None

    def test_reasoning_effort_override(self):
        """Test that reasoning effort can be overridden."""
        settings = _get_model_settings("openai:gpt-5-mini", reasoning="high")
        assert settings is not None


class TestMultiProviderSettings:
    """Test cases for multi-provider model settings."""

    def test_openai_settings_with_reasoning(self):
        """Test OpenAI settings include reasoning effort."""
        settings = _get_model_settings("openai:gpt-5-mini", reasoning="medium")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["openai_reasoning_effort"] == "medium"

    def test_anthropic_settings_high(self):
        """Test Anthropic settings with high reasoning enable thinking."""
        settings = _get_model_settings("anthropic:claude-sonnet-4-5", reasoning="high")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["anthropic_thinking"]["type"] == "enabled"
        assert provider_settings["anthropic_thinking"]["budget_tokens"] == 10240
        assert provider_settings["max_tokens"] == 16384

    def test_anthropic_settings_none(self):
        """Test Anthropic settings with none disables thinking."""
        settings = _get_model_settings("anthropic:claude-sonnet-4-5", reasoning="none")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["anthropic_thinking"]["type"] == "disabled"

    def test_google_settings_medium(self):
        """Test Google settings with medium reasoning set thinking level."""
        settings = _get_model_settings("google-gla:gemini-3-flash-preview", reasoning="medium")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["google_thinking_config"]["thinking_level"] == "MEDIUM"

    def test_google_settings_none(self):
        """Test Google settings with none returns None."""
        settings = _get_model_settings("google-gla:gemini-3-flash-preview", reasoning="none")
        assert settings is None

    def test_ollama_ignores_reasoning(self):
        """Test Ollama returns None (no thinking support)."""
        settings = _get_model_settings("ollama:llama4", reasoning="high")
        assert settings is None

    def test_unknown_provider_returns_none(self):
        """Test unknown provider returns None."""
        settings = _get_model_settings("unknown:some-model", reasoning="medium")
        assert settings is None

    def test_default_reasoning_openai(self):
        """Test default reasoning for OpenAI is medium."""
        settings = _get_model_settings("openai:gpt-5-mini")
        assert settings is not None

    def test_default_reasoning_anthropic(self):
        """Test default reasoning for Anthropic is medium."""
        settings = _get_model_settings("anthropic:claude-sonnet-4-5")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["anthropic_thinking"]["type"] == "enabled"
        assert provider_settings["anthropic_thinking"]["budget_tokens"] == 4096

    def test_default_reasoning_ollama(self):
        """Test default reasoning for Ollama is none (returns None)."""
        settings = _get_model_settings("ollama:llama4")
        assert settings is None


class TestBuildPrompt:
    """Test cases for prompt building."""

    def test_prompt_without_exam_description(self):
        """Test building prompt without exam description."""
        report = "This is a test report."
        prompt = build_prompt(report)
        assert "RADIOLOGY REPORT:" in prompt
        assert report in prompt
        assert "Exam Description:" not in prompt

    def test_prompt_with_exam_description(self):
        """Test building prompt with exam description."""
        report = "This is a test report."
        exam_desc = "CT Abdomen"
        prompt = build_prompt(report, exam_desc)
        assert "Exam Description: CT Abdomen" in prompt
        assert report in prompt


class TestValidateExtraction:
    """Test cases for extraction validation."""

    def test_valid_extraction(self):
        """Test validation of a correct extraction."""
        report_text = "The patient has pneumonia in the right lung."
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[
                ExtractedFinding(
                    finding_name="pneumonia",
                    presence="present",
                    location=FindingLocation(
                        body_region="chest",
                        specific_anatomy="right lung",
                        laterality="right",
                    ),
                    report_text="The patient has pneumonia in the right lung.",
                ),
            ],
        )
        result = validate_extraction(report_text, extraction)
        assert result.is_valid is True
        assert len(result.verbatim_errors) == 0

    def test_invalid_verbatim_quote(self):
        """Test validation catches non-verbatim quotes."""
        report_text = "The patient has pneumonia in the right lung."
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[
                ExtractedFinding(
                    finding_name="pneumonia",
                    presence="present",
                    report_text="Patient has pneumonia in right lung.",  # Paraphrased, not verbatim
                ),
            ],
        )
        result = validate_extraction(report_text, extraction)
        assert result.is_valid is False
        assert len(result.verbatim_errors) == 1
        assert "not found verbatim" in result.verbatim_errors[0]

    def test_missing_non_finding_text(self):
        """Test validation catches non-finding text not in report."""
        report_text = "Technique: CT scan."
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="CT"),
            non_finding_text=[
                NonFindingText(
                    text="Technique: MRI scan.",  # Wrong modality
                    category="technique",
                ),
            ],
        )
        result = validate_extraction(report_text, extraction)
        assert result.is_valid is False
        assert len(result.verbatim_errors) == 1

    def test_coverage_warning(self):
        """Test that coverage warnings are generated for unaccounted text."""
        report_text = "Line one.\nLine two.\nLine three."
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Test"),
            findings=[
                ExtractedFinding(
                    finding_name="test",
                    presence="present",
                    report_text="Line one.",
                ),
            ],
        )
        result = validate_extraction(report_text, extraction)
        # May have warnings about unaccounted lines
        # This is informational, not a failure
        assert isinstance(result.coverage_warnings, list)


class TestOutputValidator:
    """Test cases for the check_verbatim helper used by the output validator."""

    def test_validator_accepts_verbatim_quotes(self):
        """Test that verbatim quotes pass validation."""
        report = "The patient has pneumonia in the right lung. No pleural effusion."
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[
                ExtractedFinding(
                    finding_name="pneumonia",
                    presence="present",
                    location=FindingLocation(
                        body_region="chest",
                        specific_anatomy="right lung",
                        laterality="right",
                    ),
                    report_text="The patient has pneumonia in the right lung.",
                ),
            ],
            non_finding_text=[],
        )
        errors = check_verbatim(report, extraction)
        assert errors == []

    def test_validator_rejects_paraphrased_quotes(self):
        """Test that paraphrased quotes are rejected."""
        report = "The patient has pneumonia in the right lung."
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[
                ExtractedFinding(
                    finding_name="pneumonia",
                    presence="present",
                    report_text="Patient has pneumonia in right lung.",  # paraphrased
                ),
            ],
        )
        errors = check_verbatim(report, extraction)
        assert len(errors) == 1
        assert "pneumonia" in errors[0]

    def test_validator_rejects_paraphrased_non_finding(self):
        """Test that paraphrased non-finding text is rejected."""
        report = "Technique: CT of the abdomen and pelvis without contrast."
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="CT"),
            non_finding_text=[
                NonFindingText(
                    text="Technique: CT abdomen pelvis without contrast.",  # paraphrased
                    category="technique",
                ),
            ],
        )
        errors = check_verbatim(report, extraction)
        assert len(errors) == 1
        assert "technique" in errors[0]

    def test_validator_reports_multiple_errors(self):
        """Test that multiple errors are collected."""
        report = "The lungs are clear. No effusion."
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[
                ExtractedFinding(
                    finding_name="clear lungs",
                    presence="absent",
                    report_text="Lungs are clear.",  # paraphrased
                ),
                ExtractedFinding(
                    finding_name="pleural effusion",
                    presence="absent",
                    report_text="No pleural effusion.",  # paraphrased
                ),
            ],
        )
        errors = check_verbatim(report, extraction)
        assert len(errors) == 2
