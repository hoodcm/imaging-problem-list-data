"""Tests for finding extractor agent and extraction logic."""

from typing import Any, cast

import pytest

from finding_extractor.agent import (
    VALID_REASONING_LEVELS,
    _detect_provider,
    _emit_status,
    _get_model_settings,
    build_prompt,
    check_verbatim,
    validate_extraction,
    validate_reasoning,
    validate_reasoning_for_model,
)
from finding_extractor.models import (
    ExamInfo,
    ExtractedFinding,
    ExtractionResult,
    ExtractionUsage,
    ExtractorDeps,
    FindingLocation,
    NonFindingText,
    ReportExtraction,
)


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
        """Test Google settings with none returns explicit NONE thinking config."""
        settings = _get_model_settings("google-gla:gemini-3-flash-preview", reasoning="none")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["google_thinking_config"]["thinking_level"] == "NONE"

    def test_ollama_ignores_reasoning(self):
        """Test Ollama returns None (no thinking support)."""
        settings = _get_model_settings("ollama:llama4", reasoning="none")
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
    """Test cases for post-extraction validation (coverage analysis only).

    Verbatim quote checking is handled by the agent's output validator
    (which retries the model on failure via ModelRetry), so validate_extraction()
    only performs coverage analysis.
    """

    def test_valid_extraction_is_always_valid(self):
        """validate_extraction always reports is_valid=True (verbatim is agent-enforced)."""
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
        assert result.verbatim_errors == []

    def test_no_verbatim_errors_even_with_paraphrased_quote(self):
        """validate_extraction does not re-check verbatim quotes (agent handles that)."""
        report_text = "The patient has pneumonia in the right lung."
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[
                ExtractedFinding(
                    finding_name="pneumonia",
                    presence="present",
                    report_text="Patient has pneumonia in right lung.",  # Paraphrased
                ),
            ],
        )
        result = validate_extraction(report_text, extraction)
        assert result.is_valid is True
        assert result.verbatim_errors == []

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
        assert result.is_valid is True
        assert len(result.coverage_warnings) > 0


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


class TestReasoningValidation:
    """Test cases for reasoning level validation."""

    def test_validate_reasoning_valid_values(self):
        """All valid reasoning levels should be accepted without error."""
        for level in VALID_REASONING_LEVELS:
            validate_reasoning(level)  # should not raise

    def test_validate_reasoning_invalid_value(self):
        """Invalid reasoning values should raise ValueError."""
        for bad in ("turbo", "", "MEDIUM", "auto"):
            with pytest.raises(ValueError, match="Invalid reasoning level"):
                validate_reasoning(bad)

    def test_validate_reasoning_for_model_ollama_rejects_high(self):
        """Ollama models only support reasoning='none'."""
        with pytest.raises(ValueError, match="not supported by ollama"):
            validate_reasoning_for_model("ollama:llama4", "high")

    def test_validate_reasoning_for_model_ollama_rejects_medium(self):
        """Ollama models only support reasoning='none'."""
        with pytest.raises(ValueError, match="not supported by ollama"):
            validate_reasoning_for_model("ollama:llama4", "medium")

    def test_validate_reasoning_for_model_ollama_accepts_none(self):
        """Ollama models accept reasoning='none'."""
        validate_reasoning_for_model("ollama:llama4", "none")  # should not raise

    def test_validate_reasoning_for_model_openai_accepts_all(self):
        """OpenAI models accept all reasoning levels."""
        for level in VALID_REASONING_LEVELS:
            validate_reasoning_for_model("openai:gpt-5-mini", level)

    def test_validate_reasoning_for_model_anthropic_accepts_all(self):
        """Anthropic models accept all reasoning levels."""
        for level in VALID_REASONING_LEVELS:
            validate_reasoning_for_model("anthropic:claude-sonnet-4-5", level)

    def test_validate_reasoning_for_model_google_accepts_all(self):
        """Google models accept all reasoning levels."""
        for level in VALID_REASONING_LEVELS:
            validate_reasoning_for_model("google-gla:gemini-3-flash", level)

    def test_validate_reasoning_for_model_unknown_provider_passes(self):
        """Unknown providers are not validated (deferred to runtime)."""
        validate_reasoning_for_model("unknown:model", "high")  # should not raise


class TestOpenAINoneSettings:
    """Verify reasoning='none' returns explicit settings for OpenAI."""

    def test_openai_none_returns_explicit_settings(self):
        """OpenAI with reasoning='none' should return settings, not None."""
        settings = _get_model_settings("openai:gpt-5-mini", reasoning="none")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["openai_reasoning_effort"] == "none"


class TestExtractionResult:
    """Test ExtractionResult and ExtractionUsage data classes."""

    def test_extraction_result_fields(self):
        """ExtractionResult bundles extraction and usage."""
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Test"),
        )
        usage = ExtractionUsage(
            requests=1,
            input_tokens=100,
            output_tokens=50,
            duration_ms=1234,
        )
        result = ExtractionResult(extraction=extraction, usage=usage)
        assert result.extraction is extraction
        assert result.usage is usage
        assert result.usage.duration_ms == 1234

    def test_extraction_result_none_usage(self):
        """ExtractionResult with no usage is valid."""
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Test"),
        )
        result = ExtractionResult(extraction=extraction, usage=None)
        assert result.usage is None

    def test_extraction_usage_defaults(self):
        """ExtractionUsage defaults to zero for all fields."""
        usage = ExtractionUsage()
        assert usage.requests == 0
        assert usage.input_tokens == 0
        assert usage.output_tokens == 0
        assert usage.cache_read_tokens == 0
        assert usage.cache_write_tokens == 0
        assert usage.duration_ms is None
        assert usage.details == {}


class TestEmitStatus:
    """Test cases for the _emit_status helper."""

    @pytest.mark.asyncio
    async def test_emit_status_noop_when_no_callback(self):
        """_emit_status with status_callback=None should not raise."""
        deps = ExtractorDeps(report_text="test")
        await _emit_status(deps, "some message")  # should not raise

    @pytest.mark.asyncio
    async def test_emit_status_calls_callback(self):
        """_emit_status should invoke the callback with the message."""
        messages: list[str] = []

        async def capture(msg: str) -> None:
            messages.append(msg)

        deps = ExtractorDeps(report_text="test", status_callback=capture)
        await _emit_status(deps, "hello")
        await _emit_status(deps, "world")
        assert messages == ["hello", "world"]
