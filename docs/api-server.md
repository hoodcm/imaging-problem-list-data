# API Server Plan and Implementation Status

## Purpose

Expose `ExtractionStore` through a FastAPI JSON API so clients can:
- submit reports
- trigger asynchronous extraction jobs
- poll job status
- inspect extractions
- record corrections

The async pipeline uses TaskIQ + Redis, with SQLite as the persistence source of truth for reports, extractions, corrections, and jobs.

## Current Status (MVP)

Implemented:
1. FastAPI app with the 9 planned `/api/*` endpoints.
2. TaskIQ worker path with Redis stream broker + result backend.
3. SQLite WAL configuration for API + worker concurrency.
4. Job lifecycle persistence (`pending`/`running`/`completed`/`failed`) in `jobs` table.
5. Docker image and Compose setup (`redis`, `api`, `worker`) with shared `/data` volume.
6. Unit tests for store and API behavior.
7. Smoke script for end-to-end API flow.

Remaining (post-MVP hardening):
1. Router/service decomposition and stronger dependency-injection boundaries.
2. Real worker-process integration tests in CI (not just in-memory broker tests).
3. Redis-backed lifecycle test automation.
4. Containerized E2E smoke in CI.
5. Model-options discovery endpoint (`GET /api/models`) is planned but not yet implemented.

## Architecture

### Data and Execution Flow

1. Client `POST /api/reports` to upsert report text.
2. Client `POST /api/reports/{report_id}/extract` to queue work.
3. API creates a `jobs` row (`pending`) before enqueue.
4. TaskIQ worker receives task and marks job `running`.
5. Worker runs extraction and validation, stores extraction row, marks job `completed` with `extraction_id`.
6. On failure, worker marks job `failed` with a sanitized public error string.
7. Client polls `GET /api/jobs/{job_id}` until terminal state.

### Source-of-Truth Choices

- Job status source of truth: SQLite `jobs` table (not transient queue state).
- Job IDs: API-generated UUID string; passed through queue payload and used in polling endpoint.
- Failure detail exposure: API returns stable public error codes only (sensitive details are logged server-side).

## SQLite Concurrency and Safety

Each DB connection applies:
- `PRAGMA journal_mode=WAL`
- `PRAGMA busy_timeout=5000`
- `PRAGMA synchronous=NORMAL`
- `PRAGMA foreign_keys=ON`

This supports API + worker access on one host with short write transactions.

## TaskIQ and DI Wiring

Implemented modules:
- `src/finding_extractor/broker.py`
- `src/finding_extractor/tasks.py`
- `src/finding_extractor/api.py`

Important implementation detail:
- `taskiq_fastapi.init(broker, "finding_extractor.api:app")` is configured in `broker.py` so the standalone worker CLI path has DI context.

Worker command:
```bash
uv run taskiq worker finding_extractor.broker:broker finding_extractor.tasks
```

## Architecture Gaps To Address Next

Current implementation is stable but not fully aligned with preferred FastAPI structure:
- `src/finding_extractor/api.py` still combines app wiring, schema models, and all route handlers in one module.
- Route handlers are reasonably thin, but not yet "very thin"; orchestration and response-mapping logic is still in handlers.
- Configuration is resolved via direct `os.getenv(...)` reads rather than a centralized injected settings dependency.

These are maintainability concerns, not MVP blockers.

## HTTP API Surface

### Reports
- `POST /api/reports`
- `GET /api/reports`
- `GET /api/reports/{report_id}`

### Extractions and Jobs
- `POST /api/reports/{report_id}/extract`
- `GET /api/jobs/{job_id}`
- `GET /api/reports/{report_id}/extractions`
- `GET /api/extractions/{extraction_id}`

### Corrections
- `POST /api/extractions/{extraction_id}/corrections`
- `GET /api/extractions/{extraction_id}/corrections`

## Job Status and Error Semantics

### Trigger endpoint
`POST /api/reports/{report_id}/extract`:
- Returns `202 Accepted` on enqueue success.
- Sets `Location: /api/jobs/{job_id}` and `Retry-After: 2`.

### Poll endpoint
`GET /api/jobs/{job_id}`:
- `404` if job does not exist.
- `200` with status in `pending|running|completed|failed`.
- Frontend clients must treat `failed` as an expected terminal state and surface `jobs.error` to users/logs.

### Public `jobs.error` values
- Enqueue failure: `enqueue_failed:queue_unavailable`
- Worker failures: one of
  - `extraction_failed:invalid_request`
  - `extraction_failed:model_provider_error`
  - `extraction_failed:model_output_validation_failed`
  - `extraction_failed:model_timeout`
  - `extraction_failed:internal_error`

## Containerization (Current)

### Dockerfile
- Base image: `ghcr.io/astral-sh/uv:python3.13-bookworm-slim` (digest pinned).
- Uses `uv sync --locked --no-install-project` then `uv sync --locked` for layer reuse.
- Runs as non-root user.
- Creates and owns `/data` for SQLite volume writes.

### docker-compose.yml
Services:
1. `caddy` (`caddy:2-alpine`) — reverse proxy serving the frontend at `/` and proxying `/api/*` to the `api` service
2. `redis` (`redis:7.2-alpine`)
3. `api` (same app image; command `uv run finding-extractor-api`)
4. `worker` (same app image; TaskIQ worker command)

Both `api` and `worker`:
- load `.env`
- share `finding_extractor_db` volume mounted to `/data`
- set `FINDING_EXTRACTOR_DB_PATH=/data/finding_extractor.db`

Healthchecks:
- `redis`: `redis-cli ping` (5s interval, 5 retries)
- `api`: `python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/api/reports')"` (5s interval, 10 retries, 10s start period)
- Service ordering uses `depends_on` with `condition: service_healthy`

## Verification and Tooling

### Local tests
```bash
uv run ruff check src tests
uv run pytest
```

### Compose smoke
```bash
docker compose up -d --build --wait
bash scripts/smoke_api.sh
```

### Integration tests (E2E via Docker Compose)
```bash
uv run pytest -m integration -v
```

Notes:
- Real-model extraction is nondeterministic; smoke/integration tests may occasionally see `extraction_failed:model_output_validation_failed` even when infrastructure is healthy. The agent retries verbatim validation up to 3 times (`output_retries=3`) with whitespace-tolerant matching, but genuine paraphrasing by the model can still exhaust retries.

## Implementation Files

### New
- `src/finding_extractor/api.py`
- `src/finding_extractor/broker.py`
- `src/finding_extractor/tasks.py`
- `tests/test_api.py`
- `tests/test_tasks.py`
- `Dockerfile`
- `docker-compose.yml`
- `.dockerignore`
- `scripts/smoke_api.sh`

### Modified
- `src/finding_extractor/store.py`
- `src/finding_extractor/__init__.py`
- `tests/test_store.py`
- `pyproject.toml`
- `uv.lock`

## Post-MVP Hardening

1. Refactor API into explicit router modules (`APIRouter`) and keep app bootstrap thin.
   - Suggested split: `routers/reports.py`, `routers/extractions.py`, `routers/corrections.py`, `routers/jobs.py`.
2. Introduce service-layer modules for orchestration and keep handlers as transport adapters only.
   - Suggested services: extraction dispatch/status service, correction service.
3. Introduce centralized settings dependency for configuration DI.
   - Replace ad-hoc `os.getenv(...)` calls in API/task paths with one injected settings object.
4. Add real worker-process DI integration test (TaskIQ worker CLI path).
5. Add Redis-backed job lifecycle integration test.
6. Add container E2E smoke in CI.
7. Add provider/auth gate tests for stable failure-code behavior.
8. Add model-options discovery endpoint for UI/API clients.
   - Add endpoint: `GET /api/models`
   - Response should return provider/model options appropriate for the current deployment.
   - Build options from a maintained capability registry (provider, model id, reasoning support, default recommendation).
   - Filter returned options based on credential availability (for example: show OpenAI models only when `OPENAI_API_KEY` is configured, Anthropic only when `ANTHROPIC_API_KEY` is configured, etc.).
   - Include a conservative fallback option policy when no provider credentials are available (empty list or explicitly flagged local/offline options).
