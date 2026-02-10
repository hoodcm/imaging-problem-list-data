# Configuration System Plan

## 2026-02-10 Reassessment (Priority and Scope)

After reviewing FastAPI/Pydantic guidance, this remains a good next step, but should be
executed in a lighter sequence:

1. **After migration foundation** (`docs/migration-architecture.md`) so schema work is safe first.
2. **Env-first settings centralization** (single `Settings` object, keep existing env names).
3. **Optional TOML layer** only if needed for local ergonomics; not required for the first pass.

Rationale:
- FastAPI recommends settings via dependency injection and caching patterns.
- `pydantic-settings` is the standard settings path in Pydantic.
- Environment-first config remains the least surprising runtime contract across local/Docker/CI.

Prerequisite status:
- Migration foundation is implemented (`docs/migration-architecture.md`, Alembic baseline
  `17f8ebc6c608`), so this config plan is now the active next planning priority.

## Problem Statement

Configuration is currently scattered across the codebase as ad-hoc `os.getenv()` calls with
duplicated defaults. The same setting (e.g., `FINDING_EXTRACTOR_DB_PATH`) is resolved
independently in `api.py`, `cli.py`, `tasks.py`, and `broker.py`, each with its own fallback
logic. There is no single source of truth for what settings exist, what their defaults are, or
what types they expect.

### Current state (every config touchpoint)

| Setting | Where resolved | Default |
|---------|---------------|---------|
| `OPENAI_API_KEY` | `.env`, docker-compose `env_file` | (none) |
| `FINDING_EXTRACTOR_DB_PATH` | `api.py:165`, `cli.py:49-56` | `.finding_extractor.db` |
| `FINDING_EXTRACTOR_REDIS_URL` | `broker.py:8` | `redis://localhost:6379` |
| `FINDING_EXTRACTOR_MODEL` | `agent.py:264`, `tasks.py:53`, `cli.py:46` | `openai:gpt-5-mini` |
| `FINDING_EXTRACTOR_REASONING` | `agent.py:233` | (per-provider default) |
| `FINDING_EXTRACTOR_CORS_ORIGINS` | `api.py:171-176` | `localhost:8000` |

Problems:
1. **Duplicated resolution** -- `_resolve_db_path()` exists in both `api.py` and `cli.py` with
   slightly different signatures.
2. **No validation** -- A misspelled env var silently falls through to defaults.
3. **Secrets mixed with config** -- The `.env` file contains both API keys and is also used for
   non-secret settings in `docker-compose.yml`.
4. **No discoverability** -- A new developer has no way to see all available settings without
   reading every source file.

## Design Principles

1. **Secrets from environment only** -- API keys and credentials come from `.env` files or
   environment variables. Never from checked-in config files.
2. **Environment-first config** -- Runtime configuration should work entirely from env vars.
3. **TOML is optional** -- `config.toml` can be added later for developer ergonomics, but should
   not be required for deployment/runtime correctness.
4. **Single source of truth** -- One `Settings` class that every module imports. No more
   `os.getenv()` scattered across files.
5. **Validated at startup** -- Pydantic validates all settings when the app starts. Typos and
   bad values fail fast with clear error messages.

## Technology Choice: `pydantic-settings`

[pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) is the
standard configuration library in the Pydantic ecosystem. It supports:

- **TOML config files** natively via `TomlConfigSettingsSource` (Python 3.11+ uses stdlib
  `tomllib`, no extra dependency needed)
- **`.env` files** for secrets
- **Layered resolution** with customizable priority order
- **`SecretStr` type** that redacts values in logs/repr
- **Nested config** via Pydantic sub-models
- **FastAPI integration** via `Depends()` + `@lru_cache`

This replaces all ad-hoc `os.getenv()` calls with zero new non-Pydantic dependencies (we
already depend on `pydantic>=2.0`; `pydantic-settings` is a lightweight companion package).

## Proposed Settings Structure

Note: the sample below shows the optional TOML-enabled variant. For the first implementation
pass, omit TOML source wiring and keep env/dotenv/defaults only.

### New file: `src/finding_extractor/config.py`

```python
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, SecretStr
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    TomlConfigSettingsSource,
)


class DatabaseConfig(BaseModel):
    """SQLite persistence settings."""
    path: Path = Path(".finding_extractor.db")


class RedisConfig(BaseModel):
    """Redis connection settings for TaskIQ broker."""
    url: str = "redis://localhost:6379"
    result_ttl: int = 3600


class ExtractionConfig(BaseModel):
    """Agent and model defaults."""
    default_model: str = "openai:gpt-5-mini"
    default_reasoning: str | None = None  # None = per-provider default
    output_retries: int = 3


class ServerConfig(BaseModel):
    """API server settings."""
    host: str = "0.0.0.0"
    port: int = 8001
    cors_origins: list[str] = [
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]


class Settings(BaseSettings):
    """Application settings -- single source of truth.

    Resolution order (highest priority first):
    1. Constructor kwargs (for tests)
    2. Environment variables (prefixed FINDING_EXTRACTOR_)
    3. .env file (secrets)
    4. config.toml (structured config)
    5. Field defaults (coded above)
    """

    model_config = SettingsConfigDict(
        env_prefix="FINDING_EXTRACTOR_",
        env_file=".env",
        env_nested_delimiter="__",
        toml_file="config.toml",
        extra="ignore",
    )

    # -- Secrets (from .env / environment only) --
    openai_api_key: SecretStr | None = None
    anthropic_api_key: SecretStr | None = None

    # -- Structured config (from TOML, overridable by env) --
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    extraction: ExtractionConfig = ExtractionConfig()
    server: ServerConfig = ServerConfig()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            TomlConfigSettingsSource(settings_cls),
            file_secret_settings,
        )


@lru_cache
def get_settings() -> Settings:
    """Cached singleton -- call from FastAPI Depends() or module-level."""
    return Settings()
```

### New file: `config.toml` (checked into repo)

```toml
# config.toml -- Application configuration (non-secret)
# Override any value with env var: FINDING_EXTRACTOR_<SECTION>__<KEY>
# e.g., FINDING_EXTRACTOR_DATABASE__PATH=/data/app.db

[database]
path = ".finding_extractor.db"

[redis]
url = "redis://localhost:6379"
result_ttl = 3600

[extraction]
default_model = "openai:gpt-5-mini"
# default_reasoning is unset -- uses per-provider default

[server]
host = "0.0.0.0"
port = 8001
cors_origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]
```

### `.env` (gitignored, secrets only)

```env
# Secrets only -- never commit this file
OPENAI_API_KEY=sk-proj-...
# ANTHROPIC_API_KEY=sk-ant-...
```

Note: pydantic-settings with `env_prefix="FINDING_EXTRACTOR_"` will look for
`FINDING_EXTRACTOR_OPENAI_API_KEY` in the environment. However, since the LLM provider
libraries (openai, anthropic) read their own standard env vars (`OPENAI_API_KEY`,
`ANTHROPIC_API_KEY`) directly, we should keep those as-is in `.env` and NOT prefix them. The
`Settings` class will have `openai_api_key` without a prefix -- we handle this by using
`env_prefix` for app-specific settings and defining the API key fields with explicit
`alias` or `validation_alias` to read the standard env var names:

```python
    openai_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="OPENAI_API_KEY",
    )
    anthropic_api_key: SecretStr | None = Field(
        default=None,
        validation_alias="ANTHROPIC_API_KEY",
    )
```

This way:
- App settings use the `FINDING_EXTRACTOR_` prefix: `FINDING_EXTRACTOR_DATABASE__PATH`
- API keys use the standard names the provider SDKs expect: `OPENAI_API_KEY`
- Both are resolved by the same Settings object

## Migration Plan (Revised)

### Phase 1: Add env-first `config.py` (non-breaking)

1. Add `pydantic-settings` to `pyproject.toml` dependencies.
2. Create `src/finding_extractor/config.py` with `Settings` and `get_settings()`.
3. Keep compatibility with existing env names (`FINDING_EXTRACTOR_DB_PATH`,
   `FINDING_EXTRACTOR_REDIS_URL`, `FINDING_EXTRACTOR_MODEL`, etc.) in this phase.
4. Write tests for env/default resolution and precedence.

### Phase 2: Wire `Settings` into existing modules (one at a time)

Each module change is independent and can be a separate commit:

**`broker.py`** -- Replace `os.getenv("FINDING_EXTRACTOR_REDIS_URL", ...)` with
`get_settings().redis.url`:

```python
# Before:
_redis_url = os.getenv("FINDING_EXTRACTOR_REDIS_URL", "redis://localhost:6379")

# After:
from finding_extractor.config import get_settings
_settings = get_settings()
_redis_url = _settings.redis.url
```

**`agent.py`** -- Replace `os.getenv("FINDING_EXTRACTOR_MODEL", DEFAULT_MODEL)` and
`os.getenv("FINDING_EXTRACTOR_REASONING")` with settings:

```python
# Before (appears 3 times):
model = os.getenv("FINDING_EXTRACTOR_MODEL", DEFAULT_MODEL)

# After:
from finding_extractor.config import get_settings
settings = get_settings()
model = settings.extraction.default_model
```

**`api.py`** -- Replace `_resolve_db_path()` and `_resolve_cors_origins()`:

```python
# Before:
def _resolve_db_path() -> Path:
    db_path = os.getenv("FINDING_EXTRACTOR_DB_PATH")
    if db_path:
        return Path(db_path)
    return Path(".finding_extractor.db")

def _resolve_cors_origins() -> list[str]:
    raw = os.getenv("FINDING_EXTRACTOR_CORS_ORIGINS")
    ...

# After:
from finding_extractor.config import get_settings
settings = get_settings()
# Use settings.database.path and settings.server.cors_origins directly
```

Delete `_resolve_db_path()` and `_resolve_cors_origins()` -- they become one-liners.

**`cli.py`** -- Replace `_resolve_db_path()` and `_resolve_model_name()`:

```python
# Before:
def _resolve_db_path(db_path: Path | None) -> Path:
    if db_path is not None:
        return db_path
    env_path = os.getenv("FINDING_EXTRACTOR_DB_PATH")
    ...

# After:
from finding_extractor.config import get_settings
settings = get_settings()
resolved = db_path or settings.database.path
```

Delete `_resolve_db_path()` and `_resolve_model_name()`.

**`tasks.py`** -- Replace `os.getenv("FINDING_EXTRACTOR_MODEL", DEFAULT_MODEL)`:

```python
# Before:
model_name = model or os.getenv("FINDING_EXTRACTOR_MODEL", DEFAULT_MODEL)

# After:
from finding_extractor.config import get_settings
model_name = model or get_settings().extraction.default_model
```

### Phase 3: Compose/docs cleanup

1. Keep current compose behavior working with existing env names.
2. Update docs to declare `config.py` as the single source of truth.
3. Add a short operator-facing list of supported env vars.

### Phase 4 (Optional): Add TOML layer

If local developer ergonomics need it, add `config.toml` + `TomlConfigSettingsSource` as a
lower-priority source than env/dotenv. This is optional and should not be a prerequisite for
runtime correctness.

### Phase 5: Clean up

1. Remove all direct `os.getenv()` calls from application code (they should only exist in
   `config.py` via pydantic-settings).
2. Remove the deleted helper functions (`_resolve_db_path`, `_resolve_cors_origins`,
   `_resolve_model_name`).
3. Remove `DEFAULT_MODEL` constant from `agent.py` -- it now lives in
   `ExtractionConfig.default_model`.
4. Update `CLAUDE.md` to document the new config system.

## Testing Strategy

Minimum must-have tests for Phase 1/2:
- defaults without env
- env override for each existing supported variable name
- stable cache behavior (`get_settings.cache_clear()` in tests before assertions)
- CLI argument values still override settings defaults where expected

```python
# tests/test_config.py

def test_defaults_without_toml_or_env(tmp_path, monkeypatch):
    """Settings load with sensible defaults when no config files exist."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FINDING_EXTRACTOR_DATABASE__PATH", raising=False)
    settings = Settings()
    assert settings.database.path == Path(".finding_extractor.db")
    assert settings.extraction.default_model == "openai:gpt-5-mini"

def test_toml_overrides_defaults(tmp_path, monkeypatch):
    """TOML values take precedence over field defaults."""
    (tmp_path / "config.toml").write_text('[extraction]\ndefault_model = "anthropic:claude-sonnet-4-5"')
    monkeypatch.chdir(tmp_path)
    settings = Settings()
    assert settings.extraction.default_model == "anthropic:claude-sonnet-4-5"

def test_env_overrides_toml(tmp_path, monkeypatch):
    """Environment variables take precedence over TOML."""
    (tmp_path / "config.toml").write_text('[extraction]\ndefault_model = "anthropic:claude-sonnet-4-5"')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FINDING_EXTRACTOR_EXTRACTION__DEFAULT_MODEL", "ollama:llama3")
    settings = Settings()
    assert settings.extraction.default_model == "ollama:llama3"

def test_secrets_from_env(monkeypatch):
    """API keys resolve from standard env var names."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-123")
    settings = Settings()
    assert settings.openai_api_key.get_secret_value() == "sk-test-123"

def test_constructor_overrides_everything():
    """Explicit kwargs have highest priority (for test fixtures)."""
    settings = Settings(
        database=DatabaseConfig(path=Path("/tmp/test.db")),
        extraction=ExtractionConfig(default_model="test:model"),
    )
    assert settings.database.path == Path("/tmp/test.db")
```

## External References (Primary)

- FastAPI settings pattern (`BaseSettings` + dependency + cache):  
  https://fastapi.tiangolo.com/advanced/settings/
- Pydantic settings (`BaseSettings`, env loading, aliases, nested env):  
  https://docs.pydantic.dev/latest/concepts/pydantic_settings/

## Files Changed

| File | Change |
|------|--------|
| `pyproject.toml` | Add `pydantic-settings>=2.0` dependency |
| `src/finding_extractor/config.py` | **New** -- Settings class |
| `config.toml` | **New** -- Default configuration |
| `.gitignore` | Add `config.local.toml` |
| `src/finding_extractor/broker.py` | Use `get_settings().redis.url` |
| `src/finding_extractor/agent.py` | Use `get_settings().extraction.*`, remove `DEFAULT_MODEL` export |
| `src/finding_extractor/api.py` | Use `get_settings()`, delete `_resolve_*` helpers |
| `src/finding_extractor/cli.py` | Use `get_settings()`, delete `_resolve_*` helpers |
| `src/finding_extractor/tasks.py` | Use `get_settings().extraction.default_model` |
| `docker-compose.yml` | Use `__` delimiter env vars, mount `config.toml` |
| `tests/test_config.py` | **New** -- Settings resolution tests |
| `CLAUDE.md` | Document new config system |

## Dependency Addition

```toml
# pyproject.toml
dependencies = [
    ...
    "pydantic-settings>=2.0",
]
```

`pydantic-settings` is a lightweight package (Pydantic team, same release cadence). On
Python 3.13 it uses stdlib `tomllib` for TOML parsing -- no extra transitive dependencies.
