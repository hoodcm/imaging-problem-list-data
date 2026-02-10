"""Tests for centralized settings resolution."""

from pathlib import Path

from finding_extractor.config import (
    DEFAULT_CORS_ORIGINS,
    DEFAULT_DB_PATH,
    DEFAULT_MODEL,
    DEFAULT_REDIS_URL,
    get_settings,
)


def test_settings_defaults_without_env(tmp_path, monkeypatch):
    """Defaults should match current runtime behavior."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FINDING_EXTRACTOR_DB_PATH", raising=False)
    monkeypatch.delenv("FINDING_EXTRACTOR_REDIS_URL", raising=False)
    monkeypatch.delenv("FINDING_EXTRACTOR_MODEL", raising=False)
    monkeypatch.delenv("FINDING_EXTRACTOR_REASONING", raising=False)
    monkeypatch.delenv("FINDING_EXTRACTOR_CORS_ORIGINS", raising=False)

    settings = get_settings()

    assert settings.db_path == DEFAULT_DB_PATH
    assert settings.redis_url == DEFAULT_REDIS_URL
    assert settings.default_model == DEFAULT_MODEL
    assert settings.default_reasoning is None
    assert settings.cors_origins == DEFAULT_CORS_ORIGINS


def test_settings_support_existing_env_names(tmp_path, monkeypatch):
    """Legacy FINDING_EXTRACTOR_* names remain supported."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FINDING_EXTRACTOR_DB_PATH", "/tmp/legacy.db")
    monkeypatch.setenv("FINDING_EXTRACTOR_REDIS_URL", "redis://localhost:6380")
    monkeypatch.setenv("FINDING_EXTRACTOR_MODEL", "ollama:llama3")
    monkeypatch.setenv("FINDING_EXTRACTOR_REASONING", "low")
    monkeypatch.setenv(
        "FINDING_EXTRACTOR_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    )

    settings = get_settings()

    assert settings.db_path == Path("/tmp/legacy.db")
    assert settings.redis_url == "redis://localhost:6380"
    assert settings.default_model == "ollama:llama3"
    assert settings.default_reasoning == "low"
    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:5173"]


def test_settings_support_nested_aliases(tmp_path, monkeypatch):
    """New nested-style names are accepted for forward compatibility."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FINDING_EXTRACTOR_DATABASE__PATH", "/tmp/nested.db")
    monkeypatch.setenv("FINDING_EXTRACTOR_REDIS__URL", "redis://localhost:6390")
    monkeypatch.setenv("FINDING_EXTRACTOR_REDIS__RESULT_TTL", "120")
    monkeypatch.setenv("FINDING_EXTRACTOR_EXTRACTION__DEFAULT_MODEL", "openai:gpt-5")
    monkeypatch.setenv("FINDING_EXTRACTOR_EXTRACTION__DEFAULT_REASONING", "high")
    monkeypatch.setenv("FINDING_EXTRACTOR_SERVER__CORS_ORIGINS", " , ")

    settings = get_settings()

    assert settings.db_path == Path("/tmp/nested.db")
    assert settings.redis_url == "redis://localhost:6390"
    assert settings.redis_result_ttl == 120
    assert settings.default_model == "openai:gpt-5"
    assert settings.default_reasoning == "high"
    assert settings.cors_origins == ["*"]
