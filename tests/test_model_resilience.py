"""Tests for model resilience helpers (fallback + request concurrency)."""

from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.models.fallback import FallbackModel

from finding_extractor.llm_config.resilience import (
    PinnedModelSettingsModel,
    ProviderConcurrencyLimitedModel,
    build_resilient_model,
    clear_provider_limiters,
    get_provider_request_limiter,
    provider_scope_key,
    should_fallback_on_exception,
)


def test_provider_scope_key_uses_provider_for_known_model_ids():
    assert provider_scope_key("openai:gpt-5-mini") == "openai"
    assert provider_scope_key("anthropic:claude-sonnet-4-5") == "anthropic"


def test_provider_scope_key_uses_prefix_for_unknown_models():
    assert provider_scope_key("custom-provider:model-a") == "custom-provider"
    assert provider_scope_key("custom-model") == "custom-model"


def test_get_provider_request_limiter_is_shared_per_provider_and_limit():
    clear_provider_limiters()
    limiter_a = get_provider_request_limiter("openai:gpt-5-mini", 4)
    limiter_b = get_provider_request_limiter("openai:gpt-5", 4)
    limiter_c = get_provider_request_limiter("openai:gpt-5-mini", 2)
    assert limiter_a is limiter_b
    assert limiter_a is not limiter_c


def test_should_fallback_on_exception_handles_provider_and_timeout_failures():
    provider_error = ModelHTTPError(status_code=429, model_name="openai:gpt-5-mini")
    assert should_fallback_on_exception(provider_error) is True
    assert should_fallback_on_exception(TimeoutError("timeout")) is True
    assert should_fallback_on_exception(UnexpectedModelBehavior("bad output")) is False


def test_build_resilient_model_without_fallback_keeps_agent_level_settings(monkeypatch):
    clear_provider_limiters()
    monkeypatch.setattr(
        "finding_extractor.llm_config.resilience.get_model_settings",
        lambda model, reasoning=None: {"model": model, "reasoning": reasoning},
    )

    runtime = build_resilient_model("test", reasoning="low")

    assert runtime.model_settings == {"model": "test", "reasoning": "low"}
    assert runtime.model.model_name == "test"


def test_build_resilient_model_with_fallback_uses_pinned_settings_and_shared_limiter(
    monkeypatch,
):
    clear_provider_limiters()
    monkeypatch.setattr(
        "finding_extractor.llm_config.resilience.get_model_settings",
        lambda model, reasoning=None: {"model": model, "reasoning": reasoning},
    )

    runtime = build_resilient_model(
        "test",
        reasoning="high",
        fallback_model_name="test",
        provider_request_max_concurrency=3,
    )

    assert runtime.model_settings is None
    assert isinstance(runtime.model, FallbackModel)

    primary = runtime.model.models[0]
    fallback = runtime.model.models[1]
    assert isinstance(primary, PinnedModelSettingsModel)
    assert isinstance(fallback, PinnedModelSettingsModel)
    assert primary._pinned_model_settings == {"model": "test", "reasoning": "high"}
    assert fallback._pinned_model_settings == {"model": "test", "reasoning": "high"}

    assert isinstance(primary.wrapped, ProviderConcurrencyLimitedModel)
    assert isinstance(fallback.wrapped, ProviderConcurrencyLimitedModel)
    assert primary.wrapped._limiter is fallback.wrapped._limiter
