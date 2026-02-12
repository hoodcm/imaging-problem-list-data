# Logging Usage

Operator-facing guide for runtime logging in the finding extractor stack.

## Quick Start

Use env vars to control log output:

```bash
export IPL_LOG_LEVEL=INFO
export IPL_LOG_JSON=false
```

- `IPL_LOG_LEVEL`: `CRITICAL|ERROR|WARNING|INFO|DEBUG|NOTSET` (`WARN` accepted)
- `IPL_LOG_JSON`: set `true` for machine-readable JSON logs

## Where Logging Is Configured

Logging is initialized once per process in all runtimes:

- API (`finding-extractor-api`)
- worker (`taskiq worker`)
- CLI (`finding-extractor`)
- batch CLI (`finding-extractor-batch`)
- eval CLI (`finding-extractor-eval`)

The worker should continue to run with TaskIQ `--no-configure-logging` so the project logging pipeline stays authoritative.

## Structured Context You Can Expect

Common context fields:

- `timestamp`
- `level`
- `logger`
- `event`

API request logs also include:

- `request_id`
- `http_method`
- `http_path`
- `trace_id` and `span_id` when OpenTelemetry span context is active

Worker extraction logs include:

- `job_id`
- `report_id`

## Logfire

Logfire is optional and disabled by default.

```bash
export IPL_LOGFIRE_ENABLED=true
```

Related settings (`IPL_LOGFIRE_*`) are documented in `docs/configuration.md`.

## PHI-Safe Logging Rules

- Never log raw report text.
- Never log verbatim quote text from findings.
- Prefer IDs, counts, statuses, durations, and model names.

## Related Docs

- `docs/configuration.md`
- `docs/logging-internals.md`
