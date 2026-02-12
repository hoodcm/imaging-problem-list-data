# Logging Plan

**Status:** Stages 1 and 2 implemented; Stage 3 pending.
This remains the staged plan and acceptance guide for completing context binding and selective callsite migration.

## Goals

- Keep one logging approach across API, CLI, and worker.
- Improve structure and context (request/job IDs) without a large rewrite.
- Keep Logfire integration working as-is.
- Avoid re-implementing lifecycle behavior already provided by TaskIQ/FastAPI.

## Non-Goals (for now)

- No new database tables.
- No custom log queue/dispatcher service.
- No full migration of every module to `structlog.get_logger()` in the first pass.
- No custom Uvicorn logging config file unless we hit a concrete need.

## Current Baseline (February 11, 2026)

- `src/finding_extractor/observability.py` configures Logfire + instrumentation once per process.
- App code uses stdlib logging (`logging.getLogger(__name__)`).
- API initializes Logfire in `create_app()`.
- CLI initializes Logfire in command entrypoint.
- Worker currently calls `configure_logfire(runtime="worker")` inside `_run_extraction_impl()` (per job entry, but idempotent).

## Design Decisions

1. Keep stdlib callsites initially. Add structured formatting centrally, then migrate callsites selectively.
2. Use structlog's stdlib integration pattern (`ProcessorFormatter` + `wrap_for_formatter`) rather than custom intercept handlers.
3. Configure logging once per process:
   - API: app startup path.
   - CLI: command startup.
   - Worker: TaskIQ `WORKER_STARTUP` hook (not per-task setup).
4. Use `structlog.contextvars` for request/job correlation IDs.
5. Enforce PHI-safe field policy for all structured logs.

## Target Architecture (minimal v1)

- New module: `src/finding_extractor/logging_setup.py`
- Public function: `setup_logging(settings: Settings, *, include_logfire_processor: bool) -> None`
- Idempotent (module lock + configured flag), same style as `configure_logfire`.
- Root logger gets one `StreamHandler` with `structlog.stdlib.ProcessorFormatter`.
- `structlog.configure(...)` uses stdlib logger factory and ends with `ProcessorFormatter.wrap_for_formatter`.
- Renderer:
  - `ConsoleRenderer` when `IPL_LOG_JSON=false`
  - `JSONRenderer` when `IPL_LOG_JSON=true`

This gives structured logs immediately for existing stdlib callsites, and allows gradual move to `structlog.get_logger()` later.

## Configuration

Add to `Settings` in `src/finding_extractor/config.py`:

| Env var | Field | Default | Notes |
|---|---|---|---|
| `IPL_LOG_LEVEL` | `log_level` | `INFO` | Standard Python levels |
| `IPL_LOG_JSON` | `log_json` | `false` | JSON output for machine parsing |

No new config file is required.

## Staged Implementation Plan

### Stage 1: Logging Foundation

Scope:
- Add `structlog` dependency.
- Add `log_level` and `log_json` settings.
- Add `src/finding_extractor/logging_setup.py` with idempotent `setup_logging(...)`.
- Keep all existing logger callsites untouched.

Files:
- `pyproject.toml`
- `src/finding_extractor/config.py`
- `src/finding_extractor/logging_setup.py`
- `tests/test_config.py`
- `tests/test_logging_setup.py` (new)

Acceptance criteria:
- CLI emits structured logs in JSON mode.
- Existing stdlib loggers still work.
- Calling `setup_logging()` repeatedly does not duplicate handlers.

### Stage 2: Runtime Wiring (No Behavioral Surprises)

Scope:
- API: call logging setup once during app startup path.
- CLI: call logging setup in command entrypoint before heavy work (both `finding-extractor` and `finding-extractor-eval`).
- Batch CLI: call logging setup in group callback before subcommands.
- Worker: move one-time setup to TaskIQ startup event:
  - `@broker.on_event(TaskiqEvents.WORKER_STARTUP)`
  - configure Logfire once
  - configure logging once
- Remove per-job `configure_logfire(runtime="worker")` from `_run_extraction_impl()`.

Files:
- `src/finding_extractor/api.py`
- `src/finding_extractor/cli.py`
- `src/finding_extractor/tasks.py`
- `src/finding_extractor/broker.py` (or worker init module)
- tests for startup-hook behavior

Acceptance criteria:
- Worker no longer does observability setup per task.
- API/CLI/worker all use same formatter pipeline.
- No duplicate log lines after startup.

### Stage 3: Context + Selective Callsite Migration

Scope:
- Add request context middleware for API (`request_id`, method, path).
- In API request middleware, bind `trace_id` and `span_id` when an active OpenTelemetry span context is present (best-effort; no-op if absent).
- Bind worker context per task (`job_id`, `report_id`) with `clear_contextvars()` then `bind_contextvars(...)`.
- Convert high-value modules first (`tasks.py`, `api.py`, `api_services.py`) to structured key/value logging style.
- Run a focused logging coverage sweep across the codebase after Stage 2 to ensure a coherent execution trace at INFO/DEBUG without log spam.
- Keep low-value callsites on stdlib until touched for other work.

Coverage sweep rubric:
- Add logs at major lifecycle boundaries (startup/shutdown, request entry/exit, job state transitions, provider calls, persistence write/read boundaries).
- Prefer one informative structured log over multiple noisy logs inside tight loops.
- Keep payloads concise and PHI-safe; log IDs, counts, durations, and decision points.
- Do not add logs for trivial pass-through helpers unless they materially aid debugging.

Acceptance criteria:
- API logs include `request_id`.
- API logs include `trace_id`/`span_id` whenever tracing context is available.
- Worker logs include `job_id` and `report_id`.
- Exception logs retain traceback and structured context.
- For one representative API extraction flow and one CLI batch flow, logs form an understandable step-by-step trace at INFO; DEBUG adds diagnostic detail without duplicating INFO lines.

### Stage 4: Cleanup (Optional)

Scope:
- Migrate remaining module-level loggers to structlog wrappers where useful.
- Decide whether to capture and normalize Uvicorn access logs beyond defaults.
- Add dashboards/queries in Logfire based on stable fields.

This stage is explicitly deferrable.

## PHI Safety Rules (required in Stage 1)

- Never log raw report text.
- Never log verbatim finding quote text.
- Prefer identifiers and counts:
  - allowed: `report_id`, `job_id`, status, durations, model name.
  - avoid: free-form user text fields unless scrubbed.
- Keep error messages stable/public where possible (`to_public_job_error` style).

## Test Plan

- Unit:
  - settings parsing for `IPL_LOG_LEVEL`/`IPL_LOG_JSON`.
  - `setup_logging()` idempotency and handler count.
  - renderer switch (console vs json) by config.
- Integration:
  - worker startup event executes once at worker start.
  - task execution logs include bound context keys.
  - API request log line includes `request_id`.
  - API request log line includes `trace_id`/`span_id` when span context exists, and middleware remains silent/no-error when it does not.
  - end-to-end smoke flow emits a coherent lifecycle trace (request -> enqueue -> worker run -> store update -> completion/failure).

## Deferred Risks / Follow-ups

- Uvicorn access logs may still need dedicated tuning if field shape is inconsistent.
- Contextvars behavior in mixed sync/async boundaries should be monitored; if needed, add explicit binds in boundary points.
- If log volume is too high, add sampling/rate limiting later.

## Later Improvements Appendix

- Consider adding `structlog.stdlib.PositionalArgumentsFormatter()` into the processor chain before rendering. This can improve compatibility for any callsites that still use `%s`-style positional logging arguments while we continue staged migration.
- Consider tightening worker startup hook typing from a generic event object to `TaskiqState` once we confirm this stays stable across current TaskIQ versions and does not complicate testing ergonomics.

## Implementation Order (PR-friendly)

1. Stage 1 only.
2. Stage 2 only.
3. Stage 3 only.
4. Stage 4 optional backlog.

Each stage should merge independently and keep the system running.

## References

- structlog stdlib integration and `ProcessorFormatter`: https://www.structlog.org/en/stable/standard-library.html
- structlog contextvars guidance: https://www.structlog.org/en/stable/contextvars.html
- TaskIQ broker events (`WORKER_STARTUP`): https://taskiq-python.github.io/guide/state-and-deps.html
- Logfire `StructlogProcessor` API: https://logfire.pydantic.dev/docs/reference/api/logfire/#logfire.StructlogProcessor
