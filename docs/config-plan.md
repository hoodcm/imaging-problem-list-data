# Configuration System Plan

## 2026-02-10 Reassessment (Priority and Scope)

After reviewing FastAPI/Pydantic guidance, this remains a good next step, but should be
executed in a lighter sequence:

1. **After migration foundation** (`docs/migration-architecture.md`) so schema work is safe first.
2. **Env-first settings centralization** (single `Settings` object with a clear `IPL_*` namespace).
3. **Optional TOML layer** for local ergonomics with env precedence and no secrets in file.

Rationale:
- FastAPI recommends settings via dependency injection and caching patterns.
- `pydantic-settings` is the standard settings path in Pydantic.
- Environment-first config remains the least surprising runtime contract across local/Docker/CI.

Prerequisite status:
- Migration foundation is implemented (`docs/migration-architecture.md`, Alembic baseline
  `17f8ebc6c608`).
- With config Phase 1/2 complete, data-model consolidation planning is now the next priority
  (`docs/data-model-plan.md`).

## Status (2026-02-10)

Implemented (Phase 1/2 complete + TOML ergonomics):
- Added `pydantic-settings` dependency.
- Added centralized env-first settings in `src/finding_extractor/config.py` with cached
  `get_settings()` and a single `IPL_*` app-config namespace.
- Added optional `config.toml` source for non-secret app settings, with precedence
  `env > toml > defaults`.
- Wired `agent.py`, `api.py`, `cli.py`, `tasks.py`, and `broker.py` to use `get_settings()`
  instead of ad-hoc `os.getenv()` calls.
- Added config regression coverage in `tests/test_config.py`.
- Added cache-isolation fixture in `tests/conftest.py` for deterministic env-var tests.
- Added runtime reference doc at `docs/configuration.md` to avoid duplicated config docs.

Remaining (optional/deferred):
- Any deeper config UX simplification beyond env-first behavior.

## Original Problem Statement (Pre-Implementation)

Configuration was scattered across the codebase as ad-hoc `os.getenv()` calls with
duplicated defaults. The same setting (e.g., `IPL_DB_PATH`) is resolved
independently in `api.py`, `cli.py`, `tasks.py`, and `broker.py`, each with its own fallback
logic. There is no single source of truth for what settings exist, what their defaults are, or
what types they expect.

### Pre-centralization state (historical touchpoints)

| Setting | Where resolved | Default |
|---------|---------------|---------|
| `OPENAI_API_KEY` | `.env`, docker-compose `env_file` | (none) |
| `IPL_DB_PATH` | `api.py`, `cli.py` | `.finding_extractor.db` |
| `IPL_REDIS_URL` | `broker.py` | `redis://localhost:6379` |
| `IPL_MODEL` | `agent.py`, `tasks.py`, `cli.py` | `openai:gpt-5-mini` |
| `IPL_REASONING` | `agent.py` | (per-provider default) |
| `IPL_CORS_ORIGINS` | `api.py` | `localhost:8000` |

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
3. **TOML is optional** -- `config.toml` is supported for developer ergonomics, but should
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

## Implemented Settings Structure

Implementation lives in `src/finding_extractor/config.py` and is intentionally flat for a
lightweight codebase:

```python
class Settings(BaseSettings):
    db_path: Path
    redis_url: str
    redis_result_ttl: int
    default_model: str
    default_reasoning: str | None
    openai_api_key: str | None
    anthropic_api_key: str | None
    google_api_key: str | None
    update_model_list_interval_seconds: int
    cors_origins_raw: str

    @property
    def cors_origins(self) -> list[str]:
        ...
```

Design notes:
- Env-first with `.env` support (`model_config.env_file = ".env"`).
- App settings use `IPL_*` env vars.
- Provider credentials always use provider-native names:
  `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GOOGLE_API_KEY`.
- CORS accepts comma-separated values and JSON-list input.
- Provider credentials are accepted via standard provider env names.
- Model-catalog refresh cadence is configurable via env (`IPL_MODEL_LIST_UPDATE_INTERVAL`).
- `default_model` is validated at settings load via shared `validate_model_id(...)` policy.

## Implementation Summary

Completed in this phase:
1. Added `pydantic-settings` dependency.
2. Added centralized settings in `src/finding_extractor/config.py`.
3. Replaced ad-hoc env resolution in:
   - `src/finding_extractor/agent.py`
   - `src/finding_extractor/api.py`
   - `src/finding_extractor/broker.py`
   - `src/finding_extractor/cli.py`
   - `src/finding_extractor/tasks.py`
4. Added settings tests in `tests/test_config.py`.
5. Added settings cache reset fixture in `tests/conftest.py`.

Remaining (optional):
1. Additional settings surface simplification if usage complexity grows.

## Testing Strategy (Implemented)

Config coverage currently validates:
- default values without env vars
- `IPL_*` env names for app configuration
- provider-native API key env names
- cached settings isolation between tests via fixture cache clear

Relevant tests:
- `tests/test_config.py`
- `tests/conftest.py` (autouse cache reset fixture)

## External References (Primary)

- FastAPI settings pattern (`BaseSettings` + dependency + cache):  
  https://fastapi.tiangolo.com/advanced/settings/
- Pydantic settings (`BaseSettings`, env loading, aliases, nested env):  
  https://docs.pydantic.dev/latest/concepts/pydantic_settings/

## Files Changed (Actual)

| File | Change |
|------|--------|
| `pyproject.toml` | Added `pydantic-settings>=2.0` dependency |
| `src/finding_extractor/config.py` | New settings module |
| `src/finding_extractor/agent.py` | Use centralized model/reasoning settings |
| `src/finding_extractor/api.py` | Use centralized DB/CORS settings |
| `src/finding_extractor/broker.py` | Use centralized Redis settings |
| `src/finding_extractor/cli.py` | Use centralized model/DB settings |
| `src/finding_extractor/tasks.py` | Use centralized default model |
| `tests/test_config.py` | New settings resolution coverage |
| `tests/conftest.py` | Added settings cache isolation fixture |
| `Taskfile.yml` | `test:unit` includes config tests |
