"""Tests for provider model selection and supersession filtering."""

from pathlib import Path

import pytest

from finding_extractor.core.config import Settings
from finding_extractor.llm.catalog import (
    CatalogModel,
    ModelCatalogService,
    model_ids_equivalent,
    output_model_prefix,
    select_sota_model_ids,
)


def test_select_sota_openai_replaces_older_generations():
    selected = select_sota_model_ids(
        "openai",
        {
            "gpt-4",
            "gpt-5",
            "gpt-4.1-mini",
            "gpt-5-mini",
        },
    )

    selected_ids = {model_id for _, model_id in selected}
    assert "gpt-5" in selected_ids
    assert "gpt-5-mini" in selected_ids
    assert "gpt-4" not in selected_ids
    assert "gpt-4.1-mini" not in selected_ids


def test_select_sota_anthropic_replaces_older_minor_versions():
    selected = select_sota_model_ids(
        "anthropic",
        {
            "claude-sonnet-4-0",
            "claude-sonnet-4-5",
        },
    )

    assert selected == [("sonnet", "claude-sonnet-4-5")]


def test_select_sota_google_replaces_older_generations():
    selected = select_sota_model_ids(
        "google",
        {
            "gemini-2.0-flash",
            "gemini-2.5-flash",
        },
    )

    assert selected == []


def test_select_sota_google_allows_only_gemini_3_pro_and_flash():
    selected = select_sota_model_ids(
        "google",
        {
            "gemini-2.5-pro",
            "gemini-3-pro",
            "gemini-3-flash",
            "gemini-3.1-flash",
        },
    )
    assert selected == [("flash", "gemini-3.1-flash"), ("pro", "gemini-3-pro")]


def test_select_sota_openai_prefers_stable_alias_over_stamped_variant():
    selected = select_sota_model_ids(
        "openai",
        {
            "gpt-5-mini-20250215",
            "gpt-5-mini",
        },
    )
    assert selected == [("mini", "gpt-5-mini")]


def test_select_sota_anthropic_prefers_stable_alias_over_stamped_variant():
    selected = select_sota_model_ids(
        "anthropic",
        {
            "claude-sonnet-4-5-20250215",
            "claude-sonnet-4-5",
        },
    )
    assert selected == [("sonnet", "claude-sonnet-4-5")]


def test_select_sota_anthropic_excludes_non_45_46():
    selected = select_sota_model_ids(
        "anthropic",
        {
            "claude-sonnet-4-0",
            "claude-haiku-4-1",
        },
    )
    assert selected == []


def test_google_model_ids_are_equivalent_across_prefix_aliases():
    assert model_ids_equivalent(
        "google-gla:gemini-3-flash-preview",
        "google-gla:gemini-3-flash-preview",
    )
    assert not model_ids_equivalent(
        "google-gla:gemini-3-flash-preview",
        "google-gla:gemini-3.1-pro-preview",
    )


def test_output_prefix_for_google_is_gla():
    assert output_model_prefix("google") == "google-gla"


def test_default_catalog_model_accepts_google_preview_default():
    settings = Settings.model_construct(
        db_path=Path(".finding_extractor.db"),
        default_model="google-gla:gemini-3-flash-preview",
        redis_url="redis://localhost:6379",
        update_model_list_interval_seconds=172800,
    )
    service = ModelCatalogService(settings)

    model = service._default_catalog_model()
    assert model is not None
    assert model.id == "google-gla:gemini-3-flash-preview"
    assert model.provider == "google"
    assert model.tier == "flash"
    assert model.is_default is True


def test_catalog_model_carries_reasoning_capabilities():
    """CatalogModel with explicit capability fields should preserve them."""
    model = CatalogModel(
        id="openai:gpt-5-mini",
        provider="openai",
        tier="mini",
        supported_reasoning=["high", "low", "medium", "minimal", "none"],
        default_reasoning="medium",
    )
    assert model.supported_reasoning == ["high", "low", "medium", "minimal", "none"]
    assert model.default_reasoning == "medium"


def test_catalog_model_defaults_for_backward_compat():
    """CatalogModel with no capability fields should default safely."""
    model = CatalogModel(
        id="openai:gpt-5-mini",
        provider="openai",
        tier="mini",
    )
    assert model.supported_reasoning == []
    assert model.default_reasoning == "none"


def test_cache_key_is_v2():
    """Cache key must be v2 to force refresh after schema change."""
    settings = Settings.model_construct(
        db_path=Path(".finding_extractor.db"),
        default_model="openai:gpt-5-mini",
        redis_url="redis://localhost:6379",
        update_model_list_interval_seconds=172800,
    )
    service = ModelCatalogService(settings)
    assert "v2" in service.cache_key


@pytest.mark.asyncio
async def test_get_catalog_falls_back_when_redis_is_unavailable(monkeypatch):
    settings = Settings.model_construct(
        db_path=Path(".finding_extractor.db"),
        default_model="openai:gpt-5-mini",
        redis_url="redis://localhost:6379",
        update_model_list_interval_seconds=172800,
        openai_api_key=None,
        anthropic_api_key=None,
        google_api_key=None,
    )
    service = ModelCatalogService(settings)

    async def fail_read():
        raise RuntimeError("redis read failure")

    async def fail_refresh():
        raise RuntimeError("redis refresh failure")

    async def fake_discover_safe():
        return [
            CatalogModel(
                id="openai:gpt-5-mini",
                provider="openai",
                tier="mini",
                is_default=True,
                supported_reasoning=["high", "low", "medium", "minimal", "none"],
                default_reasoning="medium",
            )
        ]

    monkeypatch.setattr(service, "_read_cache", fail_read)
    monkeypatch.setattr(service, "_refresh_cache", fail_refresh)
    monkeypatch.setattr(service, "_discover_models_safe", fake_discover_safe)

    catalog = await service.get_catalog()
    assert catalog.stale is True
    assert len(catalog.models) == 1
    assert catalog.models[0].id == "openai:gpt-5-mini"
    assert catalog.models[0].supported_reasoning == ["high", "low", "medium", "minimal", "none"]
    assert catalog.models[0].default_reasoning == "medium"


@pytest.mark.asyncio
async def test_discovered_google_model_uses_default_prefix_and_marks_default(monkeypatch):
    settings = Settings.model_construct(
        db_path=Path(".finding_extractor.db"),
        default_model="google-gla:gemini-3-flash-preview",
        openai_api_key=None,
        anthropic_api_key=None,
        google_api_key="test-key",
        redis_url="redis://localhost:6379",
        update_model_list_interval_seconds=172800,
    )
    service = ModelCatalogService(settings)

    async def fake_google_discovery():
        return "google", {"gemini-3-flash-preview"}

    monkeypatch.setattr(service, "_discover_google", fake_google_discovery)

    catalog = await service._discover_models()
    assert len(catalog) == 1
    model = catalog[0]
    assert model.id == "google-gla:gemini-3-flash-preview"
    assert model.provider == "google"
    assert model.tier == "flash"
    assert model.is_default is True
    assert model.supported_reasoning == ["high", "low", "medium", "minimal", "none"]
    assert model.default_reasoning == "low"
