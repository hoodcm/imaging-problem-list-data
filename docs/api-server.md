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
12. Alembic migration foundation with baseline revision and drift checks (`alembic/`, `alembic.ini`, `tests/test_migrations.py`).
13. Env-first centralized settings (`src/finding_extractor/config.py`) wired into API/worker/CLI paths.
14. API layer split into composition + routes + services + contracts modules (`api.py`, `api_routes.py`, `api_services.py`, `api_models.py`, `api_dependencies.py`) with no endpoint contract changes.
15. `GET /api/models` model discovery endpoint with Redis-backed catalog caching and SOTA-only filtering (superseded model generations are hidden).
16. Shared model-id policy enforcement (`model_policy.py`) wired into config/API/worker/CLI paths; `google-vertex:*` is rejected fast.

## Lean Testing Strategy (Now)

Focus on critical reliability with low process overhead.

### 1) `test:unit` (default path)

- Deterministic backend tests without external services.
- Source files:
  - `tests/test_store.py`
  - `tests/test_api.py`
  - `tests/test_tasks.py`
  - `tests/test_migrations.py`
  - `tests/test_config.py`
  - `tests/test_model_catalog.py`
  - `tests/test_model_policy.py`

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
task db:migrate
task db:migrate:stack
task db:stamp:baseline
task db:stamp:baseline:stack
task db:revision MSG="..."
task db:current
task db:heads
task db:check
task stack:up
task stack:up:full
task stack:down
```

Notes:
- Task targets are convenience wrappers.
- Deep logic lives in Python, not shell.
- `task lint` now includes migration drift validation via `task db:check`.

## Health and Readiness

API probes:
- `GET /api/healthz`: process liveness
- `GET /api/readyz`: API readiness (database path + broker backend connectivity check)

Compose API healthcheck should target `/api/readyz`.

## `/api/models` Discovery and Cache Behavior

- `GET /api/models` returns model IDs that can be passed directly to extraction requests.
- Discovery is provider-key driven:
  - `OPENAI_API_KEY` enables OpenAI model listing.
  - `ANTHROPIC_API_KEY` enables Anthropic model listing.
  - `GOOGLE_API_KEY` enables Google Gemini model listing.
- Policy guardrails (explicit):
  - Anthropic: only `4.5` and `4.6` generation model IDs are eligible.
  - Google Gemini: only `3.x` `pro` and `flash` model IDs are eligible.
- Results are filtered to latest generation per model family/tier (for example newer GPT/Gemini/Sonnet generations suppress older superseded ones).
- Catalog is cached in Redis and refreshed on-demand at most once per `FINDING_EXTRACTOR_UPDATE_MODEL_LIST_INTERVAL` (alias: `UPDATE_MODEL_LIST`, default `172800` seconds / 48 hours).
- Startup does not block on model discovery. Refresh is lazy at request time to keep lifecycle simple and avoid extra background task complexity.
- If Redis is temporarily unavailable, `/api/models` degrades gracefully by returning an uncached stale-marked discovery/fallback payload instead of `500`.

## Deferred (Later, Not Blocking Current Lean Flow)

1. Carve out deterministic provider-independent integration coverage (separate from real-LLM integration tests).
2. Add a one-command Taskfile orchestration target for stack up -> smoke -> stack down with reliable teardown semantics.
3. Remove Starlette/FastAPI middleware typing suppression in `src/finding_extractor/api.py` once dependency/type support allows a clean typed call with no suppression.
4. Continue router/service structure refinement as maintainability work.

## API Refactor Guardrail (Step 0)

Before any router/service split work, confirm explicit API contract coverage is in place:

1. Validate `tests/test_api.py` covers endpoint response shapes and key status/error semantics.
2. Add targeted contract tests for any endpoint that will be touched but lacks explicit assertions.
3. Only then begin structural refactor steps (small commits, no contract changes).
