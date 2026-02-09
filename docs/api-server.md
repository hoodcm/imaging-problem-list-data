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
1. FastAPI app with current `/api/*` endpoints for reports, jobs, extractions, and corrections.
2. Async extraction path using TaskIQ worker + Redis broker/result backend.
3. SQLite WAL/busy-timeout settings for API + worker concurrency.
4. Job lifecycle persistence in `jobs` table (`pending|running|completed|failed`).
5. Docker setup for `redis`, `api`, and `worker`.
6. Core backend tests for store, API, and task behavior.
7. Smoke test flow for end-to-end API validation.

## Lean Plan (Now)

Focus on critical reliability with low process overhead.

### 1) Use Taskfile as the command surface

Add and use `Taskfile.yml` for developer workflows:
- `lint`
- `test` / `test:unit`
- `test:smoke`
- `stack:up` / `stack:down`

Policy:
- Task targets are convenience wrappers.
- Deep logic lives in Python, not shell.

### 2) Keep testing levels lean

Current active levels:
1. `test:unit`
   - Runs deterministic backend tests without external services.
   - Source files:
     - `tests/test_store.py`
     - `tests/test_api.py`
     - `tests/test_tasks.py`
2. `test:smoke`
   - Validates end-to-end API workflow against a running backend stack.
   - Logic in Python module: `src/finding_extractor/smoke.py`

### 3) Define lint clearly

`lint` includes:
1. Ruff (`ruff check`)
2. Ty type checking (`ty check`)

Current status: `lint` (`ruff` + `ty`) is expected to pass in normal development flow.

## Deferred (Later, Not Blocking Current Lean Flow)

1. Real worker-process integration tests (API + Redis + worker CLI path).
2. Additional Redis lifecycle contract depth.
3. `GET /api/models` endpoint for model discovery.
4. Settings/DI and router/service structure refactors.
5. Remove Starlette/FastAPI middleware typing suppression in `src/finding_extractor/api.py` once dependency/type support allows a clean typed call with no suppression.
6. Add a deterministic smoke mode (provider-independent) so core API/worker infrastructure can be validated without model/provider nondeterminism.
7. Add a one-command Taskfile smoke orchestration target that brings the stack up, runs smoke, and tears the stack down reliably.

## Task Commands

Primary commands:

```bash
task lint
task test
task test:unit
task stack:up
task test:smoke
task stack:down
```

`test:smoke` defaults to `BASE_URL=http://localhost:8001` and supports overrides via environment variables consumed by `finding_extractor.smoke`.

## Smoke Runner Behavior

`src/finding_extractor/smoke.py` performs:
1. API health wait/retry.
2. Report creation.
3. Extraction trigger.
4. Job polling to terminal state.
5. Extraction detail fetch.
6. Correction create/list checks.

Failure behavior:
- Non-terminal timeout fails.
- Terminal `failed` job status fails the smoke run.
