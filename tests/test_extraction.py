"""Tests for finding extractor agent and extraction logic."""

from typing import Any, cast

import pytest

from finding_extractor.extraction_agent import (
    _emit_status,
    build_prompt,
    check_verbatim,
    create_agent,
    extract_findings,
    validate_extraction,
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
from finding_extractor.providers import (
    VALID_REASONING_LEVELS,
    detect_provider,
    get_model_settings,
    resolve_effective_reasoning,
    validate_reasoning,
    validate_reasoning_for_model,
)


class TestDetectProvider:
    """Test cases for provider detection from model strings."""

    def test_openai_prefix(self):
        assert detect_provider("openai:gpt-5-mini") == "openai"

    def test_openai_chat_prefix(self):
        assert detect_provider("openai-chat:gpt-5-mini") == "openai"

    def test_openai_responses_prefix(self):
        assert detect_provider("openai-responses:gpt-5") == "openai"

    def test_anthropic_prefix(self):
        assert detect_provider("anthropic:claude-sonnet-4-5") == "anthropic"

    def test_google_gla_prefix(self):
        assert detect_provider("google-gla:gemini-3-flash-preview") == "google"

    def test_google_vertex_prefix_not_supported(self):
        assert detect_provider("google-vertex:gemini-3-pro-preview") is None

    def test_ollama_prefix(self):
        assert detect_provider("ollama:llama4") == "ollama"

    def test_openrouter_prefix(self):
        assert detect_provider("openrouter:anthropic/claude-sonnet-4-5") == "openrouter"

    def test_bare_model_name(self):
        assert detect_provider("gpt-5-mini") is None

    def test_unknown_prefix(self):
        assert detect_provider("unknown:some-model") is None


class TestModelSettings:
    """Test cases for model settings configuration."""

    def test_default_model_settings(self):
        """Test that default OpenAI model settings are created."""
        settings = get_model_settings("openai:gpt-5-mini")
        assert settings is not None

    def test_reasoning_effort_override(self):
        """Test that reasoning effort can be overridden."""
        settings = get_model_settings("openai:gpt-5-mini", reasoning="high")
        assert settings is not None


class TestMultiProviderSettings:
    """Test cases for multi-provider model settings."""

    def test_openai_settings_with_reasoning(self):
        """Test OpenAI settings include reasoning effort."""
        settings = get_model_settings("openai:gpt-5-mini", reasoning="medium")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["openai_reasoning_effort"] == "medium"

    def test_anthropic_settings_high(self):
        """Test Anthropic settings with high reasoning enable thinking."""
        settings = get_model_settings("anthropic:claude-sonnet-4-5", reasoning="high")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["anthropic_thinking"]["type"] == "enabled"
        assert provider_settings["anthropic_thinking"]["budget_tokens"] == 10240
        assert provider_settings["max_tokens"] == 16384

    def test_anthropic_settings_none(self):
        """Test Anthropic settings with none disables thinking."""
        settings = get_model_settings("anthropic:claude-sonnet-4-5", reasoning="none")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["anthropic_thinking"]["type"] == "disabled"

    def test_google_settings_medium(self):
        """Test Google settings with medium reasoning set thinking level."""
        settings = get_model_settings("google-gla:gemini-3-flash-preview", reasoning="medium")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["google_thinking_config"]["thinking_level"] == "MEDIUM"

    def test_google_settings_none(self):
        """Test Google settings with none returns explicit NONE thinking config."""
        settings = get_model_settings("google-gla:gemini-3-flash-preview", reasoning="none")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["google_thinking_config"]["thinking_level"] == "NONE"

    def test_ollama_ignores_reasoning(self):
        """Test Ollama returns None (no thinking support)."""
        settings = get_model_settings("ollama:llama4", reasoning="none")
        assert settings is None

    def test_unknown_provider_returns_none(self):
        """Test unknown provider returns None."""
        settings = get_model_settings("unknown:some-model", reasoning="medium")
        assert settings is None

    def test_default_reasoning_openai(self):
        """Test default reasoning for OpenAI is medium."""
        settings = get_model_settings("openai:gpt-5-mini")
        assert settings is not None

    def test_default_reasoning_anthropic(self):
        """Test default reasoning for Anthropic is medium."""
        settings = get_model_settings("anthropic:claude-sonnet-4-5")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["anthropic_thinking"]["type"] == "enabled"
        assert provider_settings["anthropic_thinking"]["budget_tokens"] == 4096

    def test_default_reasoning_ollama(self):
        """Test default reasoning for Ollama is none (returns None)."""
        settings = get_model_settings("ollama:llama4")
        assert settings is None

    def test_openrouter_settings_high(self):
        """Test OpenRouter settings with high reasoning."""
        settings = get_model_settings("openrouter:anthropic/claude-sonnet-4-5", reasoning="high")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["openrouter_reasoning"]["effort"] == "high"

    def test_openrouter_settings_minimal_maps_to_low(self):
        """Test OpenRouter maps 'minimal' reasoning to 'low' effort."""
        settings = get_model_settings("openrouter:openai/gpt-5", reasoning="minimal")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["openrouter_reasoning"]["effort"] == "low"

    def test_openrouter_settings_none(self):
        """Test OpenRouter settings with none disables reasoning."""
        settings = get_model_settings("openrouter:meta-llama/llama-2-70b-chat", reasoning="none")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["openrouter_reasoning"]["enabled"] is False

    def test_openrouter_default_reasoning(self):
        """Test default reasoning for OpenRouter is medium."""
        settings = get_model_settings("openrouter:anthropic/claude-sonnet-4-5")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["openrouter_reasoning"]["effort"] == "medium"

    def test_anthropic_budget_minimal(self):
        """Test Anthropic minimal reasoning budget."""
        settings = get_model_settings("anthropic:claude-sonnet-4-5", reasoning="minimal")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["anthropic_thinking"]["budget_tokens"] == 1024
        assert provider_settings["max_tokens"] == 8192

    def test_anthropic_budget_low(self):
        """Test Anthropic low reasoning budget."""
        settings = get_model_settings("anthropic:claude-sonnet-4-5", reasoning="low")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["anthropic_thinking"]["budget_tokens"] == 1024

    def test_anthropic_budget_medium(self):
        """Test Anthropic medium reasoning budget."""
        settings = get_model_settings("anthropic:claude-sonnet-4-5", reasoning="medium")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["anthropic_thinking"]["budget_tokens"] == 4096

    def test_anthropic_budget_high(self):
        """Test Anthropic high reasoning budget."""
        settings = get_model_settings("anthropic:claude-sonnet-4-5", reasoning="high")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["anthropic_thinking"]["budget_tokens"] == 10240
        assert provider_settings["max_tokens"] == 16384

    def test_google_thinking_minimal(self):
        """Test Google minimal thinking level."""
        settings = get_model_settings("google-gla:gemini-3-pro-preview", reasoning="minimal")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["google_thinking_config"]["thinking_level"] == "MINIMAL"

    def test_google_thinking_low(self):
        """Test Google low thinking level."""
        settings = get_model_settings("google-gla:gemini-3-pro-preview", reasoning="low")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["google_thinking_config"]["thinking_level"] == "LOW"

    def test_google_thinking_high(self):
        """Test Google high thinking level."""
        settings = get_model_settings("google-gla:gemini-3-pro-preview", reasoning="high")
        assert settings is not None
        provider_settings = cast(dict[str, Any], settings)
        assert provider_settings["google_thinking_config"]["thinking_level"] == "HIGH"


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

    def test_structured_report_includes_section_hint(self):
        """Structured report with sections gets a REPORT STRUCTURE hint."""
        report = "Findings:\nNormal.\n\nImpression:\nNo acute finding."
        prompt = build_prompt(report)
        assert "REPORT STRUCTURE" in prompt
        assert "FINDINGS" in prompt
        assert "IMPRESSION" in prompt

    def test_unstructured_report_no_section_hint(self):
        """Unstructured report without recognizable headers gets no hint."""
        report = "The heart is normal. No effusion."
        prompt = build_prompt(report)
        assert "REPORT STRUCTURE" not in prompt


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

    def test_validator_accepts_whitespace_equivalent_quotes(self):
        """Whitespace-only formatting differences should still count as verbatim."""
        report = "Findings: Mild bibasilar atelectasis."
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[
                ExtractedFinding(
                    finding_name="atelectasis",
                    presence="present",
                    report_text="Findings:\n  Mild   bibasilar   atelectasis.",
                ),
            ],
        )
        errors = check_verbatim(report, extraction)
        assert errors == []

    @pytest.mark.asyncio
    async def test_extract_findings_applies_usage_request_limit(self, monkeypatch):
        """extract_findings should pass UsageLimits using configured request budget."""

        class FakeUsage:
            requests = 1
            input_tokens = 10
            output_tokens = 5
            cache_read_tokens = 0
            cache_write_tokens = 0
            details = {}

        class FakeRunResult:
            output = ReportExtraction(
                exam_info=ExamInfo(study_description="Chest XR"),
                findings=[
                    ExtractedFinding(
                        finding_name="pleural effusion",
                        presence="absent",
                        report_text="No pleural effusion.",
                    )
                ],
            )

            def usage(self):
                return FakeUsage()

        captured_kwargs: dict[str, Any] = {}

        class FakeAgent:
            async def run(self, _prompt, **kwargs):
                captured_kwargs.update(kwargs)
                return FakeRunResult()

        monkeypatch.setattr("finding_extractor.extraction_agent.create_agent", lambda *_a, **_k: FakeAgent())
        monkeypatch.setattr(
            "finding_extractor.extraction_agent.get_settings",
            lambda: type(
                "S",
                (),
                {
                    "default_model": "openai:gpt-5-mini",
                    "agent_request_limit": 7,
                },
            )(),
        )

        result = await extract_findings("No pleural effusion.")

        assert result.extraction.findings[0].finding_name == "pleural effusion"
        assert captured_kwargs["usage_limits"].request_limit == 7


class TestCreateAgent:
    """Test create_agent wiring for resilient model composition."""

    def test_create_agent_passes_resilient_model_runtime(self, monkeypatch):
        """create_agent should delegate model wiring to shared resilient agent helper."""
        captured: dict[str, Any] = {}

        class FakeAgent:
            def output_validator(self, fn):
                return fn

        def fake_create_resilient_agent(**kwargs):
            captured["kwargs"] = kwargs
            return FakeAgent()

        monkeypatch.setattr(
            "finding_extractor.extraction_agent.create_resilient_agent",
            fake_create_resilient_agent,
        )

        create_agent(reasoning="low")

        assert captured["kwargs"]["model_name"] == "openai:gpt-5-mini"
        assert captured["kwargs"]["reasoning"] == "low"
        assert captured["kwargs"]["output_type"] is ReportExtraction
        assert captured["kwargs"]["deps_type"] is ExtractorDeps
        assert captured["kwargs"]["output_retries"] == 3

    def test_create_agent_skips_model_settings_when_runtime_uses_pinned_fallback(self, monkeypatch):
        """create_agent should respect explicit model override when creating resilient agent."""
        captured: dict[str, Any] = {}

        class FakeAgent:
            def output_validator(self, fn):
                return fn

        def fake_create_resilient_agent(**kwargs):
            captured["kwargs"] = kwargs
            return FakeAgent()

        monkeypatch.setattr("finding_extractor.extraction_agent.create_resilient_agent", fake_create_resilient_agent)

        create_agent("openai:gpt-5-mini")

        assert captured["kwargs"]["model_name"] == "openai:gpt-5-mini"


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
            validate_reasoning_for_model("google-gla:gemini-3-flash-preview", level)

    def test_validate_reasoning_for_model_openrouter_accepts_all(self):
        """OpenRouter models accept all reasoning levels (including minimal)."""
        for level in VALID_REASONING_LEVELS:
            validate_reasoning_for_model("openrouter:anthropic/claude-sonnet-4-5", level)

    def test_validate_reasoning_for_model_unknown_provider_passes(self):
        """Unknown providers are not validated (deferred to runtime)."""
        validate_reasoning_for_model("unknown:model", "high")  # should not raise


class TestOpenAINoneSettings:
    """Verify reasoning='none' returns explicit settings for OpenAI."""

    def test_openai_none_returns_explicit_settings(self):
        """OpenAI with reasoning='none' should return settings, not None."""
        settings = get_model_settings("openai:gpt-5-mini", reasoning="none")
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


class TestResolveEffectiveReasoning:
    """Test cases for effective reasoning resolution and validation."""

    def test_explicit_reasoning_overrides_default(self, monkeypatch):
        """Explicit reasoning should take precedence over env default."""
        monkeypatch.setenv("IPL_REASONING", "low")
        level = resolve_effective_reasoning("openai:gpt-5-mini", "high")
        assert level == "high"

    def test_env_default_used_when_no_explicit(self, monkeypatch):
        """When no explicit reasoning, env default should be used."""
        monkeypatch.setenv("IPL_REASONING", "low")
        level = resolve_effective_reasoning("openai:gpt-5-mini")
        assert level == "low"

    def test_provider_default_used_when_no_env(self):
        """When no explicit or env default, provider default is used."""
        level = resolve_effective_reasoning("openai:gpt-5-mini")
        assert level == "medium"

    def test_ollama_default_is_none(self):
        """Ollama provider default reasoning is 'none'."""
        level = resolve_effective_reasoning("ollama:llama4")
        assert level == "none"

    def test_ollama_with_incompatible_env_default_raises(self, monkeypatch):
        """Ollama + env default 'high' should fail fast."""
        monkeypatch.setenv("IPL_REASONING", "high")
        with pytest.raises(ValueError, match="not supported by ollama"):
            resolve_effective_reasoning("ollama:llama4")

    def test_ollama_with_incompatible_explicit_raises(self):
        """Ollama + explicit 'medium' should fail fast."""
        with pytest.raises(ValueError, match="not supported by ollama"):
            resolve_effective_reasoning("ollama:llama4", "medium")

    def test_unknown_provider_returns_none_without_defaults(self):
        """Unknown provider with no reasoning returns None."""
        level = resolve_effective_reasoning("unknown:model")
        assert level is None

    def test_unknown_provider_with_explicit_reasoning(self):
        """Unknown provider with explicit reasoning validates and returns it."""
        level = resolve_effective_reasoning("unknown:model", "high")
        assert level == "high"


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
