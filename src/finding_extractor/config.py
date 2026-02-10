"""Centralized runtime configuration for finding_extractor."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_DB_PATH = Path(".finding_extractor.db")
DEFAULT_REDIS_URL = "redis://localhost:6379"
DEFAULT_MODEL = "openai:gpt-5-mini"
DEFAULT_CORS_ORIGINS = ["http://localhost:8000", "http://127.0.0.1:8000"]


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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return process-global settings instance."""
    return Settings()


def clear_settings_cache() -> None:
    """Clear cached settings (primarily for tests)."""
    get_settings.cache_clear()
