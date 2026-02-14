"""Provider-specific model settings configuration.

This module manages reasoning/thinking configuration for supported LLM providers:
- OpenAI (reasoning effort: none, minimal, low, medium, high)
- Anthropic (extended thinking with budget tokens)
- Google (thinking levels: NONE, MINIMAL, LOW, MEDIUM, HIGH)
- OpenRouter (effort-based reasoning: low, medium, high)
- Ollama (reasoning disabled, local models)

Each provider has:
- Default reasoning level when unspecified
- Supported reasoning levels (validation)
- Settings builder function that returns provider-specific ModelSettings
"""

from typing import get_args

from anthropic.types.beta.beta_thinking_config_disabled_param import (
    BetaThinkingConfigDisabledParam,
)
from anthropic.types.beta.beta_thinking_config_enabled_param import (
    BetaThinkingConfigEnabledParam,
)
from pydantic_ai.models.anthropic import AnthropicModelSettings
from pydantic_ai.models.google import GoogleModelSettings
from pydantic_ai.models.openai import OpenAIChatModelSettings
from pydantic_ai.models.openrouter import OpenRouterModelSettings
from pydantic_ai.settings import ModelSettings

from finding_extractor.config import get_settings
from finding_extractor.models import ReasoningLevel

# ---------------------------------------------------------------------------
# Reasoning level constants and validation
# ---------------------------------------------------------------------------

VALID_REASONING_LEVELS: tuple[str, ...] = get_args(ReasoningLevel)

# Default reasoning level per provider (when --reasoning is omitted)
PROVIDER_DEFAULT_REASONING: dict[str, str] = {
    "openai": "medium",
    "anthropic": "medium",
    "google": "medium",
    "openrouter": "medium",
    "ollama": "none",
}

PROVIDER_SUPPORTED_REASONING: dict[str, set[str]] = {
    "openai": set(VALID_REASONING_LEVELS),
    "anthropic": set(VALID_REASONING_LEVELS),
    "google": set(VALID_REASONING_LEVELS),
    "openrouter": set(VALID_REASONING_LEVELS),
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
    provider = detect_provider(model)
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


def detect_provider(model: str) -> str | None:
    """Detect the provider from a model string prefix.

    Args:
        model: Model identifier (e.g., "openai:gpt-5-mini", "anthropic:claude-sonnet-4-5")

    Returns:
        Provider name ("openai", "anthropic", "google", "openrouter", "ollama")
        or None if unknown
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
        "openrouter": "openrouter",
        "ollama": "ollama",
    }
    return prefix_map.get(prefix)


def build_openai_settings(reasoning_level: str) -> OpenAIChatModelSettings:
    """Build OpenAI model settings with reasoning effort."""
    return OpenAIChatModelSettings(openai_reasoning_effort=reasoning_level)  # type: ignore[typeddict-item]


def build_anthropic_settings(reasoning_level: str) -> AnthropicModelSettings | None:
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


def build_google_settings(reasoning_level: str) -> GoogleModelSettings:
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


def build_openrouter_settings(reasoning_level: str) -> OpenRouterModelSettings:
    """Build OpenRouter model settings with reasoning effort.

    OpenRouter supports effort-based reasoning (low, medium, high) similar to OpenAI.
    We map our "minimal" level to "low" since OpenRouter doesn't have a minimal tier.
    For "none", we disable reasoning explicitly with {"enabled": False}.
    """
    if reasoning_level == "none":
        return OpenRouterModelSettings(
            openrouter_reasoning={"enabled": False},
        )
    # Map minimal → low for OpenRouter (it only supports low/medium/high)
    effort = "low" if reasoning_level == "minimal" else reasoning_level
    return OpenRouterModelSettings(
        openrouter_reasoning={"effort": effort},  # type: ignore[typeddict-item]
    )


def get_model_settings(model: str, reasoning: str | None = None) -> ModelSettings | None:
    """Build provider-appropriate ModelSettings for the agent.

    Detects the provider from the model string and builds the corresponding
    settings with reasoning/thinking configuration.

    Args:
        model: The model identifier (e.g., "openai:gpt-5-mini")
        reasoning: Optional override for reasoning level

    Returns:
        Provider-specific ModelSettings, or None if no settings needed
    """
    provider = detect_provider(model)
    if provider is None:
        return None

    # Resolve reasoning level: explicit param > env var > provider default
    settings = get_settings()
    level = reasoning or settings.default_reasoning or PROVIDER_DEFAULT_REASONING.get(provider)
    if level is None:
        return None

    builders = {
        "openai": build_openai_settings,
        "anthropic": build_anthropic_settings,
        "google": build_google_settings,
        "openrouter": build_openrouter_settings,
    }

    builder = builders.get(provider)
    if builder is None:
        return None

    return builder(level)
