"""Tests for provider model selection and supersession filtering."""

from pathlib import Path

import pytest

from finding_extractor.config import Settings
from finding_extractor.model_catalog import (
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
    assert model_ids_equivalent("google-gla:gemini-3-flash", "google-gla:gemini-3-flash")
    assert not model_ids_equivalent("google-gla:gemini-3-flash", "google-gla:gemini-3-pro")


def test_output_prefix_for_google_is_gla():
    assert output_model_prefix("google") == "google-gla"


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
            )
        ]

    monkeypatch.setattr(service, "_read_cache", fail_read)
    monkeypatch.setattr(service, "_refresh_cache", fail_refresh)
    monkeypatch.setattr(service, "_discover_models_safe", fake_discover_safe)

    catalog = await service.get_catalog()
    assert catalog.stale is True
    assert catalog.models == [
        CatalogModel(
            id="openai:gpt-5-mini",
            provider="openai",
            tier="mini",
            is_default=True,
        )
    ]


@pytest.mark.asyncio
async def test_discovered_google_model_uses_default_prefix_and_marks_default(monkeypatch):
    settings = Settings.model_construct(
        db_path=Path(".finding_extractor.db"),
        default_model="google-gla:gemini-3-flash",
        openai_api_key=None,
        anthropic_api_key=None,
        google_api_key="test-key",
        redis_url="redis://localhost:6379",
        update_model_list_interval_seconds=172800,
    )
    service = ModelCatalogService(settings)

    async def fake_google_discovery():
        return "google", {"gemini-3-flash"}

    monkeypatch.setattr(service, "_discover_google", fake_google_discovery)

    catalog = await service._discover_models()
    assert catalog == [
        CatalogModel(
            id="google-gla:gemini-3-flash",
            provider="google",
            tier="flash",
            is_default=True,
        )
    ]
