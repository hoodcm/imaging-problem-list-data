# API Server Plan and Status (Lean)

## Purpose

Expose `ExtractionStore` through a FastAPI JSON API so clients can:
- submit reports
- trigger asynchronous extraction jobs
- poll job status
- inspect extractions
- record corrections

Persistence source of truth is SQLite (`reports`, `extractions`, `corrections`, `jobs`), with TaskIQ + Redis for async worker execution.

## Current Backend State

Implemented:
1. FastAPI app with `/api/*` endpoints for reports, jobs, extractions, corrections, and health probes (`/api/healthz`, `/api/readyz`).
2. Async extraction path using TaskIQ worker + Redis broker/result backend.
3. SQLite WAL/busy-timeout settings for API + worker concurrency.
4. Job lifecycle persistence in `jobs` table (`pending|running|completed|failed`).
5. Docker stack with `caddy`, `redis`, `api`, and `worker`.
6. API readiness now checks both database access and broker backend (Redis) connectivity before returning ready.
7. Compose healthchecks for Redis and API readiness; startup ordering uses `depends_on` + `service_healthy`.
8. Frontend/backend integration via Caddy (`/` serves frontend, `/api/*` proxies to API).
9. Core backend tests for store/API/task behavior.
10. Python smoke test flow for end-to-end API validation (`src/finding_extractor/smoke.py`).
11. Optional full-stack integration suite (`tests/test_integration.py`) for browser -> proxy -> API -> worker -> Redis coverage.

## Lean Testing Strategy (Now)

Focus on critical reliability with low process overhead.

### 1) `test:unit` (default path)

- Deterministic backend tests without external services.
- Source files:
  - `tests/test_store.py`
  - `tests/test_api.py`
  - `tests/test_tasks.py`

### 2) `test:smoke` (service-level API flow)

- Validates API workflow against a running backend stack.
- Logic in Python module: `src/finding_extractor/smoke.py`.
- Fails on timeout or terminal failed job status.

### 3) `test:integration` (optional/full stack)

- Validates integrated frontend+backend stack through Docker Compose and Caddy.
- Marked as `integration`; intentionally not part of default `task test` path.
- Best used for pre-merge confidence and stack-level regressions.

## Task Commands

Primary commands:

```bash
task lint
task test
task test:unit
task test:smoke
task test:integration
task stack:up
task stack:up:full
task stack:down
```

Notes:
- Task targets are convenience wrappers.
- Deep logic lives in Python, not shell.

## Health and Readiness

API probes:
- `GET /api/healthz`: process liveness
- `GET /api/readyz`: API readiness (database path + broker backend connectivity check)

Compose API healthcheck should target `/api/readyz`.

## Deferred (Later, Not Blocking Current Lean Flow)

1. Carve out deterministic provider-independent integration coverage (separate from real-LLM integration tests).
2. Add a one-command Taskfile orchestration target for stack up -> smoke -> stack down with reliable teardown semantics.
3. Remove Starlette/FastAPI middleware typing suppression in `src/finding_extractor/api.py` once dependency/type support allows a clean typed call with no suppression.
4. Add `GET /api/models` endpoint for model discovery.
5. Continue settings/DI and router/service structure refactors as maintainability work.
