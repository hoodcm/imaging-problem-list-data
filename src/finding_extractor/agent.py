"""Pydantic AI agent for extracting structured findings from radiology reports.

This module defines the extraction agent with:
- System prompt assembled from composable blocks (see ``prompt.py``)
- Model configuration with reasoning/thinking support (OpenAI, Anthropic, Google, Ollama)
- Structured output via Tool Output mode (default)
- Post-extraction validation (verbatim quote checking, coverage analysis)
"""

import logging
import time
from collections.abc import Awaitable, Callable
from typing import get_args

from anthropic.types.beta.beta_thinking_config_disabled_param import (
    BetaThinkingConfigDisabledParam,
)
from anthropic.types.beta.beta_thinking_config_enabled_param import (
    BetaThinkingConfigEnabledParam,
)
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.models.openai import OpenAIChatModelSettings
from pydantic_ai.settings import ModelSettings

from finding_extractor.config import get_settings
from finding_extractor.models import (
    ExtractionResult,
    ExtractionUsage,
    ExtractorDeps,
    ReasoningLevel,
    ReportExtraction,
    ValidationResult,
)
from finding_extractor.prompt import build_system_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Reasoning level constants and validation
# ---------------------------------------------------------------------------

VALID_REASONING_LEVELS: tuple[str, ...] = get_args(ReasoningLevel)

# Default reasoning level per provider (when --reasoning is omitted)
PROVIDER_DEFAULT_REASONING: dict[str, str] = {
    "openai": "medium",
    "anthropic": "medium",
    "google": "medium",
    "ollama": "none",
}

PROVIDER_SUPPORTED_REASONING: dict[str, set[str]] = {
    "openai": set(VALID_REASONING_LEVELS),
    "anthropic": set(VALID_REASONING_LEVELS),
    "google": set(VALID_REASONING_LEVELS),
    "ollama": {"none"},
}

# Anthropic thinking budget mapping: level -> (budget_tokens, max_tokens)
ANTHROPIC_THINKING_BUDGETS: dict[str, tuple[int, int]] = {
    "minimal": (1024, 8192),
    "low": (1024, 8192),
    "medium": (4096, 8192),
    "high": (10240, 16384),
}


def validate_reasoning(reasoning: str) -> ReasoningLevel:
    """Validate that *reasoning* is one of the accepted levels.

    Raises ``ValueError`` with a descriptive message when it is not.
    Returns the validated level for convenience.
    """
    if reasoning not in VALID_REASONING_LEVELS:
        allowed = ", ".join(VALID_REASONING_LEVELS)
        raise ValueError(f"Invalid reasoning level {reasoning!r}; must be one of: {allowed}")
    return reasoning  # type: ignore[return-value]


def validate_reasoning_for_model(model: str, reasoning: str) -> ReasoningLevel:
    """Validate *reasoning* is compatible with the provider behind *model*.

    Raises ``ValueError`` when the provider does not support the level
    (e.g. ``ollama:llama4`` with ``reasoning="high"``).
    Returns the validated level for convenience.
    """
    level = validate_reasoning(reasoning)
    provider = _detect_provider(model)
    if provider is None:
        return level  # unknown provider — let the agent handle it
    supported = PROVIDER_SUPPORTED_REASONING.get(provider)
    if supported is not None and reasoning not in supported:
        allowed = ", ".join(sorted(supported))
        raise ValueError(
            f"Reasoning level {reasoning!r} is not supported by {provider} models; "
            f"supported levels: {allowed}"
        )
    return level


def _detect_provider(model: str) -> str | None:
    """Detect the provider from a model string prefix.

    Args:
        model: Model identifier (e.g., "openai:gpt-5-mini", "anthropic:claude-sonnet-4-5")

    Returns:
        Provider name ("openai", "anthropic", "google", "ollama") or None if unknown
    """
    if ":" not in model:
        return None

    prefix = model.split(":")[0]
    prefix_map = {
        "openai": "openai",
        "openai-chat": "openai",
        "openai-responses": "openai",
        "anthropic": "anthropic",
        "google-gla": "google",
        "ollama": "ollama",
    }
    return prefix_map.get(prefix)


def _build_openai_settings(reasoning_level: str) -> OpenAIChatModelSettings:
    """Build OpenAI model settings with reasoning effort."""
    return OpenAIChatModelSettings(openai_reasoning_effort=reasoning_level)  # type: ignore[typeddict-item]


def _build_anthropic_settings(reasoning_level: str) -> AnthropicModelSettings | None:
    """Build Anthropic model settings with extended thinking."""
    if reasoning_level == "none":
        # Unlike OpenAI/Google, Anthropic needs an explicit disable — returning None
        # would leave agent-level defaults (thinking enabled) in effect.
        thinking: BetaThinkingConfigDisabledParam = {"type": "disabled"}
        return AnthropicModelSettings(
            anthropic_thinking=thinking,
        )
    budget_tokens, max_tokens = ANTHROPIC_THINKING_BUDGETS[reasoning_level]
    thinking: BetaThinkingConfigEnabledParam = {
        "type": "enabled",
        "budget_tokens": budget_tokens,
    }
    return AnthropicModelSettings(
        anthropic_thinking=thinking,
        max_tokens=max_tokens,
    )


def _build_google_settings(reasoning_level: str) -> GoogleModelSettings:
    """Build Google model settings with thinking level."""
    level_map = {
        "none": "NONE",
        "minimal": "MINIMAL",
        "low": "LOW",
        "medium": "MEDIUM",
        "high": "HIGH",
    }
    return GoogleModelSettings(
        google_thinking_config={"thinking_level": level_map[reasoning_level]},
    )


def _get_model_settings(model: str, reasoning: str | None = None) -> ModelSettings | None:
    """Build provider-appropriate ModelSettings for the agent.

    Detects the provider from the model string and builds the corresponding
    settings with reasoning/thinking configuration.

    Args:
        model: The model identifier (e.g., "openai:gpt-5-mini")
        reasoning: Optional override for reasoning level

    Returns:
        Provider-specific ModelSettings, or None if no settings needed
    """
    provider = _detect_provider(model)
    if provider is None:
        return None

    # Resolve reasoning level: explicit param > env var > provider default
    settings = get_settings()
    level = reasoning or settings.default_reasoning or PROVIDER_DEFAULT_REASONING.get(provider)
    if level is None:
        return None

    builders = {
        "openai": _build_openai_settings,
        "anthropic": _build_anthropic_settings,
        "google": _build_google_settings,
    }

    builder = builders.get(provider)
    if builder is None:
        return None

    return builder(level)


async def _emit_status(deps: ExtractorDeps, message: str) -> None:
    """Emit a status message via the deps callback, if one is configured."""
    if deps.status_callback is not None:
        await deps.status_callback(message)


def create_agent(model: str | None = None) -> Agent[ExtractorDeps, ReportExtraction]:
    """Create and configure the finding extraction agent.

    Args:
        model: Optional model override. Defaults to openai:gpt-5-mini or
               IPL_MODEL env var.

    Returns:
        Configured Agent instance with ReportExtraction output type
    """
    if model is None:
        model = get_settings().default_model

    instructions = build_system_prompt()
    model_settings = _get_model_settings(model)

    kwargs: dict = {
        "instructions": instructions,
        "output_type": ReportExtraction,
        "deps_type": ExtractorDeps,
        "output_retries": 3,
    }
    if model_settings is not None:
        kwargs["model_settings"] = model_settings

    agent = Agent[ExtractorDeps, ReportExtraction](model, **kwargs)

    @agent.output_validator
    async def validate_verbatim(
        ctx: RunContext[ExtractorDeps], output: ReportExtraction
    ) -> ReportExtraction:
        errors = check_verbatim(ctx.deps.report_text, output)
        if errors:
            await _emit_status(
                ctx.deps,
                f"Retrying: verbatim validation failed ({len(errors)} error(s))",
            )
            msg = "Verbatim check failed. " + errors[0]
            if len(errors) > 1:
                msg += f" (and {len(errors) - 1} more)"
            msg += ". Quote EXACTLY from the report text."
            raise ModelRetry(msg)
        return output

    return agent


def _normalize_ws(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip."""
    return " ".join(text.split())


def _verbatim_match(quote: str, report_text: str) -> bool:
    """Check if quote appears in report_text, tolerating whitespace differences."""
    if quote in report_text:
        return True
    return _normalize_ws(quote) in _normalize_ws(report_text)


def check_verbatim(report_text: str, output: ReportExtraction) -> list[str]:
    """Check that all extracted text segments appear verbatim in the report.

    Args:
        report_text: The original report text
        output: The extraction to validate

    Returns:
        List of error messages for non-verbatim quotes (empty if all pass)
    """
    errors = []
    for finding in output.findings:
        if not _verbatim_match(finding.report_text, report_text):
            errors.append(f"Finding '{finding.finding_name}': quote not found verbatim")
    for nft in output.non_finding_text:
        if not _verbatim_match(nft.text, report_text):
            errors.append(f"Non-finding ({nft.category}): text not found verbatim")
    return errors


def build_prompt(report_text: str, exam_description: str | None = None) -> str:
    """Build the user prompt for the extraction agent.

    Args:
        report_text: The full text of the radiology report
        exam_description: Optional exam description for context (e.g., modality, body part)

    Returns:
        Formatted prompt string
    """
    prompt_parts = []

    if exam_description:
        prompt_parts.append(f"Exam Description: {exam_description}")
        prompt_parts.append("")

    prompt_parts.append("RADIOLOGY REPORT:")
    prompt_parts.append("-" * 40)
    prompt_parts.append(report_text)
    prompt_parts.append("-" * 40)
    prompt_parts.append("")
    prompt_parts.append(
        "Extract all findings from this report into the structured format described above."
    )

    return "\n".join(prompt_parts)


async def extract_findings(
    report_text: str,
    exam_description: str | None = None,
    model: str | None = None,
    reasoning: str | None = None,
    status_callback: Callable[[str], Awaitable[None]] | None = None,
) -> ExtractionResult:
    """Run the extraction agent on a radiology report.

    Args:
        report_text: The full text of the radiology report
        exam_description: Optional exam description for context
        model: Optional model override
        reasoning: Optional reasoning effort override
        status_callback: Optional async callback for progress messages

    Returns:
        ExtractionResult containing extraction output and token usage
    """
    agent = create_agent(model)
    deps = ExtractorDeps(report_text=report_text, status_callback=status_callback)

    run_settings = None
    if reasoning:
        model_id = model or get_settings().default_model
        run_settings = _get_model_settings(model_id, reasoning)

    prompt = build_prompt(report_text, exam_description)

    await _emit_status(deps, "Calling model...")
    t0 = time.monotonic()
    if run_settings:
        result = await agent.run(prompt, deps=deps, model_settings=run_settings)
    else:
        result = await agent.run(prompt, deps=deps)
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    await _emit_status(deps, "Model call complete, processing results")

    # Capture token usage from the agent run
    usage: ExtractionUsage | None = None
    try:
        run_usage = result.usage()
        details: dict[str, int] = {}
        if run_usage.details:
            details = {k: v for k, v in run_usage.details.items() if isinstance(v, int)}
        usage = ExtractionUsage(
            requests=run_usage.requests,
            input_tokens=run_usage.input_tokens,
            output_tokens=run_usage.output_tokens,
            cache_read_tokens=run_usage.cache_read_tokens,
            cache_write_tokens=run_usage.cache_write_tokens,
            duration_ms=elapsed_ms,
            details=details,
        )
    except Exception:
        logger.debug("Failed to capture usage from agent run", exc_info=True)

    return ExtractionResult(extraction=result.output, usage=usage)


def validate_extraction(
    report_text: str,
    extraction: ReportExtraction,
) -> ValidationResult:
    """Validate a ReportExtraction against the original report text.

    Performs coverage analysis to identify report text segments that may have
    been skipped during extraction.  Verbatim quote checking is handled by the
    agent's output validator (which retries the model on failure), so it is not
    repeated here.

    Args:
        report_text: The original report text
        extraction: The extracted findings to validate

    Returns:
        ValidationResult with coverage warnings
    """
    coverage_warnings = []

    extracted_texts = [f.report_text for f in extraction.findings]
    extracted_texts.extend(nf.text for nf in extraction.non_finding_text)

    report_lines = report_text.split("\n")
    unaccounted_lines = []

    for line in report_lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue

        found = any(line_stripped in extracted for extracted in extracted_texts)
        if not found:
            unaccounted_lines.append(line_stripped)

    if unaccounted_lines:
        coverage_warnings.append(
            f"Some report lines may not be fully accounted for: {len(unaccounted_lines)} lines. "
            f"Example: '{unaccounted_lines[0][:80]}...'"
        )

    return ValidationResult(
        is_valid=True,
        verbatim_errors=[],
        coverage_warnings=coverage_warnings,
    )
