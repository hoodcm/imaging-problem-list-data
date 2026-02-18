# Logging Internals

Implementation notes for contributors working on logging and observability behavior.

## Scope

- Shared structured logging setup across API, worker, and CLIs
- Request/task context binding
- Logfire integration and instrumentation
- PHI-safe field policy

For runtime usage and operator controls, see `docs/logging-usage.md`.

## Module Map

| File | Role |
|---|---|
| `src/finding_extractor/logging_setup.py` | Process-global structlog + stdlib integration (`ProcessorFormatter`) |
| `src/finding_extractor/observability.py` | Logfire configuration and one-time instrumentation |
| `src/finding_extractor/api.py` | API startup logging init + request context middleware |
| `src/finding_extractor/broker.py` | worker startup hook for observability/logging init |
| `src/finding_extractor/tasks.py` | worker task context binding (`job_id`, `report_id`) |
| `src/finding_extractor/api_services.py` | enqueue lifecycle structured callsites |
| `src/finding_extractor/model_catalog.py` | structured model-discovery/cache warnings |

## Runtime Initialization Model

Design contract:

1. Initialize Logfire once per process (`configure_logfire(...)`).
2. Initialize logging once per process (`setup_logging(...)`).
3. Keep stdlib + structlog integration in one pipeline.

This avoids duplicate handlers, avoids per-task setup overhead, and keeps formatting consistent across runtimes.

## Context Binding Model

API middleware binds request-scoped context with `structlog.contextvars`:

- `request_id`
- `http_method`
- `http_path`
- optional `trace_id` and `span_id` from active OpenTelemetry span context

Worker task execution binds:

- `job_id`
- `report_id`

Both API and worker paths clear contextvars at the end of the request/task.

## Callsite Conventions

- Prefer `structlog.get_logger(__name__)` in high-value modules.
- Prefer structured key/value fields over positional `%s` formatting.
- Keep events concise and stable.
- Keep sensitive payloads out of logs (PHI-safe policy).

## Tests

Primary logging tests:

- `tests/test_logging_setup.py` (idempotency, renderer mode, Logfire processor path)
- `tests/test_api.py` (request context keys + trace/span propagation)
- `tests/test_tasks.py` (worker context keys + startup observability wiring)

## Deferred Items / Improvement Backlog

These are intentionally deferred and should be done only when justified by a concrete issue:

1. Uvicorn/access-log normalization beyond defaults if field shape becomes operationally problematic.
2. Additional context binding at async/sync boundary points if contextvars propagation gaps are observed.
3. Log volume controls (sampling/rate limiting) if production volume becomes noisy.
4. Consider `structlog.stdlib.PositionalArgumentsFormatter()` if remaining `%s` stdlib callsites create compatibility friction.
5. Consider tightening worker startup hook typing from generic event object to `TaskiqState` once compatibility and test ergonomics are confirmed.

## Historical Plan

The staged implementation plan is retained as historical context in `docs/archive/logging-plan.md`.
