"""Tests for centralized settings resolution."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from finding_extractor.config import (
    DEFAULT_CORS_ORIGINS,
    DEFAULT_DB_PATH,
    DEFAULT_MODEL,
    DEFAULT_REDIS_URL,
    DEFAULT_UPDATE_MODEL_LIST_INTERVAL_SECONDS,
    get_settings,
)


def test_settings_defaults_without_env(tmp_path, monkeypatch):
    """Defaults should match current runtime behavior."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("IPL_DB_PATH", raising=False)
    monkeypatch.delenv("IPL_REDIS_URL", raising=False)
    monkeypatch.delenv("IPL_MODEL", raising=False)
    monkeypatch.delenv("IPL_REASONING", raising=False)
    monkeypatch.delenv("IPL_CORS_ORIGINS", raising=False)

    settings = get_settings()

    assert settings.db_path == DEFAULT_DB_PATH
    assert settings.redis_url == DEFAULT_REDIS_URL
    assert settings.default_model == DEFAULT_MODEL
    assert settings.default_reasoning is None
    assert settings.openai_api_key is None
    assert settings.anthropic_api_key is None
    assert settings.google_api_key is None
    assert settings.update_model_list_interval_seconds == DEFAULT_UPDATE_MODEL_LIST_INTERVAL_SECONDS
    assert settings.cors_origins == DEFAULT_CORS_ORIGINS
    assert settings.logfire_enabled is False
    assert settings.logfire_send == "auto"


def test_settings_support_ipl_env_names(tmp_path, monkeypatch):
    """`IPL_*` environment names configure runtime settings."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IPL_DB_PATH", "/tmp/ipl.db")
    monkeypatch.setenv("IPL_REDIS_URL", "redis://localhost:6380")
    monkeypatch.setenv("IPL_MODEL", "ollama:llama3")
    monkeypatch.setenv("IPL_REASONING", "low")
    monkeypatch.setenv("OPENAI_API_KEY", "openai-test")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-test")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-test")
    monkeypatch.setenv("IPL_MODEL_LIST_UPDATE_INTERVAL", "86400")
    monkeypatch.setenv(
        "IPL_CORS_ORIGINS",
        "http://localhost:3000,http://localhost:5173",
    )

    settings = get_settings()

    assert settings.db_path == Path("/tmp/ipl.db")
    assert settings.redis_url == "redis://localhost:6380"
    assert settings.default_model == "ollama:llama3"
    assert settings.default_reasoning == "low"
    assert settings.openai_api_key == "openai-test"
    assert settings.anthropic_api_key == "anthropic-test"
    assert settings.google_api_key == "google-test"
    assert settings.update_model_list_interval_seconds == 86400
    assert settings.cors_origins == ["http://localhost:3000", "http://localhost:5173"]


def test_settings_support_logfire_env_names(tmp_path, monkeypatch):
    """Logfire settings should be configurable from env vars."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IPL_LOGFIRE_ENABLED", "true")
    monkeypatch.setenv("IPL_LOGFIRE_SEND", "false")
    monkeypatch.setenv("IPL_LOGFIRE_TOKEN", "test-token")
    monkeypatch.setenv("IPL_LOGFIRE_SERVICE", "custom-service")
    monkeypatch.setenv("IPL_LOGFIRE_ENV", "test")
    monkeypatch.setenv("IPL_LOGFIRE_HEADERS", "true")
    monkeypatch.setenv("IPL_LOGFIRE_METRICS", "true")
    monkeypatch.setenv("IPL_LOGFIRE_SDKS", "true")

    settings = get_settings()

    assert settings.logfire_enabled is True
    assert settings.logfire_send == "false"
    assert settings.logfire_token == "test-token"
    assert settings.logfire_service_name == "custom-service"
    assert settings.logfire_environment == "test"
    assert settings.logfire_capture_headers is True
    assert settings.logfire_system_metrics is True
    assert settings.logfire_instrument_provider_sdks is True


def test_settings_reject_invalid_logfire_send_value(tmp_path, monkeypatch):
    """Logfire send mode only accepts bool/auto/true/false."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IPL_LOGFIRE_SEND", "maybe")

    with pytest.raises(ValidationError, match="logfire send mode must be one of"):
        get_settings()


def test_settings_reject_disallowed_default_model_prefix(tmp_path, monkeypatch):
    """`google-vertex:*` defaults are rejected in env settings."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("IPL_MODEL", "google-vertex:gemini-3-pro")

    with pytest.raises(ValidationError, match="google-vertex models are not allowed"):
        get_settings()


def test_settings_load_non_secret_values_from_config_toml(tmp_path, monkeypatch):
    """Optional config.toml should load non-secret app settings."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        """
[ipl]
db_path = "/tmp/from-toml.db"
redis_url = "redis://localhost:6390"
default_model = "ollama:llama3.3"
default_reasoning = "none"
update_model_list_interval_seconds = 600
cors_origins_raw = "http://localhost:4200,http://localhost:5173"
logfire_enabled = true
logfire_send = "auto"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    settings = get_settings()

    assert settings.db_path == Path("/tmp/from-toml.db")
    assert settings.redis_url == "redis://localhost:6390"
    assert settings.default_model == "ollama:llama3.3"
    assert settings.default_reasoning == "none"
    assert settings.update_model_list_interval_seconds == 600
    assert settings.cors_origins == ["http://localhost:4200", "http://localhost:5173"]
    assert settings.logfire_enabled is True
    assert settings.logfire_send == "auto"


def test_env_overrides_config_toml_values(tmp_path, monkeypatch):
    """Environment variables should take precedence over config.toml."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        """
[ipl]
default_model = "ollama:llama3.3"
default_reasoning = "none"
""".strip()
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("IPL_MODEL", "openai:gpt-5-mini")
    monkeypatch.setenv("IPL_REASONING", "high")

    settings = get_settings()

    assert settings.default_model == "openai:gpt-5-mini"
    assert settings.default_reasoning == "high"


def test_settings_reject_secrets_in_config_toml(tmp_path, monkeypatch):
    """config.toml rejects secret keys to keep credentials env-only."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        """
[ipl]
openai_api_key = "should-not-be-here"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-secrets only"):
        get_settings()


def test_settings_reject_secrets_in_nested_config_toml_section(tmp_path, monkeypatch):
    """config.toml rejects secret keys even when nested in other sections."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "config.toml").write_text(
        """
[secrets]
OPENAI_API_KEY = "should-not-be-here"
""".strip()
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="non-secrets only"):
        get_settings()
