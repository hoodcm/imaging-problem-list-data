"""Centralized runtime configuration for finding_extractor."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DB_PATH = Path(".finding_extractor.db")
DEFAULT_REDIS_URL = "redis://localhost:6379"
DEFAULT_MODEL = "openai:gpt-5-mini"
DEFAULT_CORS_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]
DEFAULT_UPDATE_MODEL_LIST_INTERVAL_SECONDS = 48 * 60 * 60


class Settings(BaseSettings):
    """Environment-first app settings with compatibility aliases."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    db_path: Path = Field(
        default=DEFAULT_DB_PATH,
        validation_alias=AliasChoices(
            "FINDING_EXTRACTOR_DB_PATH",
            "FINDING_EXTRACTOR_DATABASE__PATH",
        ),
    )
    redis_url: str = Field(
        default=DEFAULT_REDIS_URL,
        validation_alias=AliasChoices(
            "FINDING_EXTRACTOR_REDIS_URL",
            "FINDING_EXTRACTOR_REDIS__URL",
        ),
    )
    redis_result_ttl: int = Field(
        default=3600,
        validation_alias=AliasChoices(
            "FINDING_EXTRACTOR_REDIS_RESULT_TTL",
            "FINDING_EXTRACTOR_REDIS__RESULT_TTL",
        ),
    )
    default_model: str = Field(
        default=DEFAULT_MODEL,
        validation_alias=AliasChoices(
            "FINDING_EXTRACTOR_MODEL",
            "FINDING_EXTRACTOR_EXTRACTION__DEFAULT_MODEL",
        ),
    )
    default_reasoning: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "FINDING_EXTRACTOR_REASONING",
            "FINDING_EXTRACTOR_EXTRACTION__DEFAULT_REASONING",
        ),
    )
    openai_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("OPENAI_API_KEY"),
    )
    anthropic_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ANTHROPIC_API_KEY"),
    )
    google_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("GOOGLE_API_KEY"),
    )
    update_model_list_interval_seconds: int = Field(
        default=DEFAULT_UPDATE_MODEL_LIST_INTERVAL_SECONDS,
        ge=60,
        validation_alias=AliasChoices(
            "FINDING_EXTRACTOR_UPDATE_MODEL_LIST_INTERVAL",
            "FINDING_EXTRACTOR_MODEL_LIST__UPDATE_INTERVAL_SECONDS",
            "UPDATE_MODEL_LIST",
            "UPDATE_MODEL_LIST_INTERVAL",
        ),
    )
    cors_origins_raw: str = Field(
        default="http://localhost:8000,http://127.0.0.1:8000",
        validation_alias=AliasChoices(
            "FINDING_EXTRACTOR_CORS_ORIGINS",
            "FINDING_EXTRACTOR_SERVER__CORS_ORIGINS",
        ),
    )

    @property
    def cors_origins(self) -> list[str]:
        """Return CORS origins from comma-separated or JSON-list input."""
        raw = self.cors_origins_raw
        if not raw.strip():
            return DEFAULT_CORS_ORIGINS.copy()

        if raw.lstrip().startswith("["):
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = None
            if isinstance(parsed, list):
                origins = [str(origin).strip() for origin in parsed if str(origin).strip()]
                return origins or ["*"]

        origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
        return origins or ["*"]

    @field_validator("default_model")
    @classmethod
    def _validate_default_model(cls, value: str) -> str:
        from finding_extractor.model_policy import validate_model_id

        validate_model_id(value)
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return process-global settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear cached settings (primarily for tests)."""
    get_settings.cache_clear()
