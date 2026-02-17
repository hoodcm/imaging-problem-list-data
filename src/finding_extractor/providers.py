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

Architecture:
- Provider detection is imported from `model_policy.py` (canonical source)
- This module focuses on runtime settings construction for extraction agent
- `model_policy.py` handles validation, SOTA filtering, and model ID parsing
"""

from dataclasses import dataclass
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
from finding_extractor.model_policy import provider_from_model_id, validate_model_id
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


# ---------------------------------------------------------------------------
# Extraction presets: named (model, reasoning) configurations
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ExtractionPreset:
    """Named (model, reasoning) configuration for common extraction profiles."""

    name: str
    model: str
    reasoning: str
    description: str


EXTRACTION_PRESETS: dict[str, ExtractionPreset] = {
    "fast": ExtractionPreset(
        name="fast",
        model="openai:gpt-5-mini",
        reasoning="none",
        description="Fast extraction, no reasoning",
    ),
    "balanced": ExtractionPreset(
        name="balanced",
        model="openai:gpt-5-mini",
        reasoning="medium",
        description="Current default behavior",
    ),
    "quality": ExtractionPreset(
        name="quality",
        model="anthropic:claude-sonnet-4-5",
        reasoning="high",
        description="Deep reasoning for complex reports",
    ),
    "local": ExtractionPreset(
        name="local",
        model="ollama:llama3.3",
        reasoning="none",
        description="Local model, no API keys needed",
    ),
}

PRESET_NAMES: tuple[str, ...] = tuple(EXTRACTION_PRESETS.keys())


def get_preset(name: str) -> ExtractionPreset:
    """Look up a preset by name (case-insensitive).

    Raises ``ValueError`` if the preset name is not recognized.
    """
    preset = EXTRACTION_PRESETS.get(name.lower())
    if preset is None:
        allowed = ", ".join(PRESET_NAMES)
        raise ValueError(f"Unknown preset {name!r}; must be one of: {allowed}")
    return preset


def validate_all_presets() -> None:
    """Verify all preset model IDs pass model policy validation."""
    for preset in EXTRACTION_PRESETS.values():
        validate_model_id(preset.model)


# ---------------------------------------------------------------------------
# Provider reasoning capability metadata
# ---------------------------------------------------------------------------


def provider_reasoning_capabilities(provider: str) -> tuple[list[str], str]:
    """Return (sorted_supported_levels, default_reasoning) for a provider.

    Used by ``model_catalog`` to enrich ``CatalogModel`` entries with
    capability metadata.  Returns ``([], "none")`` for unknown providers.
    """
    supported = PROVIDER_SUPPORTED_REASONING.get(provider)
    if supported is None:
        return [], "none"
    default = PROVIDER_DEFAULT_REASONING.get(provider, "none")
    return sorted(supported), default


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
    provider = provider_from_model_id(model)
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
        openrouter_reasoning={"effort": effort},
    )


def resolve_effective_reasoning(model: str, reasoning: str | None = None) -> str | None:
    """Resolve and validate the effective reasoning level for *model*.

    Resolution order: *reasoning* (explicit) → ``settings.default_reasoning``
    (env/config) → provider default.

    After resolution the level is validated against the provider's supported
    set so that incompatible combinations (e.g. ``ollama`` + ``"high"``) fail
    fast rather than producing a late runtime ``KeyError``.

    Returns the resolved level, or ``None`` when the provider is unknown and
    no explicit/default reasoning was given.
    """
    provider = provider_from_model_id(model)
    settings = get_settings()
    level = (
        reasoning
        or settings.default_reasoning
        or (PROVIDER_DEFAULT_REASONING.get(provider) if provider else None)
    )
    if level is None:
        return None
    # Validate resolved level against provider
    validate_reasoning_for_model(model, level)
    return level


def get_model_settings(model: str, reasoning: str | None = None) -> ModelSettings | None:
    """Build provider-appropriate ModelSettings for the agent.

    Detects the provider from the model string and builds the corresponding
    settings with reasoning/thinking configuration.  This is a pure builder —
    callers are responsible for validating compatibility via
    ``resolve_effective_reasoning()`` at preflight boundaries.

    Args:
        model: The model identifier (e.g., "openai:gpt-5-mini")
        reasoning: Optional override for reasoning level

    Returns:
        Provider-specific ModelSettings, or None if no settings needed
    """
    provider = provider_from_model_id(model)
    if provider is None:
        return None

    # Resolve reasoning level: explicit param > env var > provider default
    settings = get_settings()
    level = (
        reasoning
        or settings.default_reasoning
        or PROVIDER_DEFAULT_REASONING.get(provider)
    )
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
