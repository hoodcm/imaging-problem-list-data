# Configuration Guide

This is the canonical configuration reference for the extraction backend.

## Precedence

Configuration sources are applied in this order:

1. runtime/init arguments
2. environment variables (`IPL_*` and provider API key vars)
3. `config.toml` (optional, non-secrets only)
4. code defaults

## Environment Variables

### App Settings (`IPL_*`)

| Env var | Type | Default | TOML key (`[ipl]`) |
|---|---|---|---|
| `IPL_DB_PATH` | path | `.finding_extractor.db` | `db_path` |
| `IPL_REDIS_URL` | string | `redis://localhost:6379` | `redis_url` |
| `IPL_REDIS_RESULT_TTL` | int | `3600` | `redis_result_ttl` |
| `IPL_MODEL` | string | `openai:gpt-5-mini` | `default_model` |
| `IPL_REASONING` | string \| null | provider default | `default_reasoning` |
| `IPL_BATCH_RUN_DIR` | path | `.batch_runs` | `batch_run_dir` |
| `IPL_BATCH_WORKERS` | int | `4` | `batch_workers` |
| `IPL_BATCH_TIMEOUT_SECONDS` | int | `420` | `batch_timeout_seconds` |
| `IPL_BATCH_RETRIES` | int | `1` | `batch_retries` |
| `IPL_BATCH_STATUS_INTERVAL_SECONDS` | float | `5.0` | `batch_status_interval_seconds` |
| `IPL_BATCH_OUTPUT_SUFFIX` | string | `.extracted.json` | `batch_output_suffix` |
| `IPL_BATCH_RESUME` | bool | `true` | `batch_resume` |
| `IPL_MODEL_LIST_UPDATE_INTERVAL` | int | `172800` | `update_model_list_interval_seconds` |
| `IPL_CORS_ORIGINS` | string | `http://localhost:8000,http://127.0.0.1:8000` | `cors_origins_raw` |
| `IPL_LOG_LEVEL` | string | `INFO` | `log_level` |
| `IPL_LOG_JSON` | bool | `false` | `log_json` |
| `IPL_LOGFIRE_ENABLED` | bool | `false` | `logfire_enabled` |
| `IPL_LOGFIRE_SEND` | `auto\|true\|false` | `auto` | `logfire_send` |
| `IPL_LOGFIRE_SERVICE` | string | `finding-extractor` | `logfire_service_name` |
| `IPL_LOGFIRE_ENV` | string \| null | `null` | `logfire_environment` |
| `IPL_LOGFIRE_HEADERS` | bool | `false` | `logfire_capture_headers` |
| `IPL_LOGFIRE_METRICS` | bool | `false` | `logfire_system_metrics` |
| `IPL_LOGFIRE_SDKS` | bool | `false` | `logfire_instrument_provider_sdks` |

Notes:
- `IPL_LOG_LEVEL` accepts `CRITICAL`, `ERROR`, `WARNING`, `INFO`, `DEBUG`, `NOTSET` (`WARN` alias is normalized to `WARNING`).

### Provider API Keys (Always Unprefixed)

These are intentionally not `IPL_`-prefixed and are env-only:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`

### Logfire Secret (Env Only)

- `IPL_LOGFIRE_TOKEN`

## `config.toml` (Optional, Non-Secrets)

`config.toml` is optional and intended for local non-secret defaults.

Supported layouts:

1. top-level keys
2. `[ipl]` section

When both are present, keys from `[ipl]` win.

Example:

```toml
[ipl]
db_path = ".finding_extractor.db"
redis_url = "redis://localhost:6379"
redis_result_ttl = 3600
default_model = "openai:gpt-5-mini"
default_reasoning = "medium"
batch_run_dir = ".batch_runs"
batch_workers = 4
batch_timeout_seconds = 420
batch_retries = 1
batch_status_interval_seconds = 5.0
batch_output_suffix = ".extracted.json"
batch_resume = true
update_model_list_interval_seconds = 172800
cors_origins_raw = "http://localhost:8000,http://127.0.0.1:8000"
log_level = "INFO"
log_json = false

logfire_enabled = false
logfire_send = "auto"
logfire_service_name = "finding-extractor"
logfire_environment = "dev"
logfire_capture_headers = false
logfire_system_metrics = false
logfire_instrument_provider_sdks = false
```

Use the starter template at `config.toml.example`.

## Secrets Policy

Secrets are rejected from `config.toml`. Put them in env vars only.

Rejected TOML keys include:

- `openai_api_key`
- `anthropic_api_key`
- `google_api_key`
- `logfire_token`
- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`
- `GOOGLE_API_KEY`
- `IPL_LOGFIRE_TOKEN`

## Common Setup

```bash
# copy starter file
cp config.toml.example config.toml

# provider secret(s)
export OPENAI_API_KEY=...

# optional runtime overrides
export IPL_MODEL=anthropic:claude-sonnet-4-5
export IPL_REASONING=high
```
