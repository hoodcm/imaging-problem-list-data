# AGENTS.md

Fast onboarding notes for coding agents working in this repo.

## 1) Project in 60 seconds

This repo has three main parts:

1. Backend extractor service (`src/finding_extractor/`)
2. Extractor frontend SPA (`extractor-ui/`) for submitting reports and reviewing extractions
3. IPL viewer SPA (`viewer/`) for browsing patient-level Imaging Problem Lists from static JSON

Primary workflow:

1. Submit report text (`POST /api/reports`)
2. Queue async extraction job (`POST /api/reports/{id}/extract`)
3. Worker runs PydanticAI extraction and writes result
4. Poll job (`GET /api/jobs/{id}`) until `completed|failed`
5. Fetch extraction (`GET /api/extractions/{id}`) and optional corrections

## 2) What is source-of-truth vs planning docs

- Source of truth for behavior: code in `src/finding_extractor/`, `extractor-ui/`, `viewer/`, and tests in `tests/`.
- `docs/*-plan.md`, `docs/*-refactoring.md`, and `docs/DEV_LOG.md` are useful context but may describe proposed or partially complete work.

## 3) Read this first (highest signal)

1. `CLAUDE.md` (repo conventions + architecture map)
2. `Taskfile.yml` (actual command surface)
3. `src/finding_extractor/api.py`
4. `src/finding_extractor/api_routes.py`
5. `src/finding_extractor/tasks.py`
6. `src/finding_extractor/store.py`
7. `src/finding_extractor/agent.py`
8. `src/finding_extractor/config.py`
9. `extractor-ui/app.js`
10. `viewer/app.js`
11. `tests/test_api.py`, `tests/test_tasks.py`, `tests/test_store.py`, `tests/test_ui.py`
12. `docs/logging-usage.md`, `docs/logging-internals.md` (runtime logging behavior + contributor guidance)
13. `docs/testing-practices.md` (project-specific testing conventions)

## 4) Backend architecture quick map

- `api.py`: FastAPI app factory, lifespan wiring, CORS, `/api/healthz`, `/api/readyz`
- `api_routes.py`: route handlers only
- `api_services.py`: endpoint orchestration helpers (lookup + enqueue)
- `api_models.py`: request/response contracts + store-to-response mappers
- `tasks.py`: TaskIQ extraction task implementation + job state transitions
- `broker.py`: Redis broker and TaskIQ/FastAPI integration
- `store.py`: async SQLite persistence (reports, extractions, jobs, corrections)
- `agent.py`: PydanticAI extraction agent, prompting, provider reasoning settings, verbatim validation
- `model_policy.py`: shared model ID validation/policy
- `model_catalog.py`: multi-provider model discovery + Redis cache + SOTA filtering
- `config.py`: centralized settings (`IPL_*` + provider keys, optional `config.toml`)
- `logging_setup.py`: process-global structured logging configuration
- `observability.py`: Logfire setup + instrumentation hooks

## 5) Data + persistence mental model

SQLite tables:

1. `reports` (dedup by SHA-256 of report text)
2. `extractions` (full extraction JSON + metadata)
3. `jobs` (`pending|running|completed|failed`)
4. `corrections` (`add_finding|update_finding|comment`)

Important runtime behavior:

- API creates a `jobs` row before enqueueing.
- Worker marks `running`, then either `completed` with `extraction_id` or `failed` with a stable public error code.
- Store still runs `SQLModel.metadata.create_all()` for table bootstrap, but Alembic is present and should be used for schema evolution.

## 6) API contract notes worth remembering

- All API routes are under `/api`.
- Trigger extraction payload field is `validate` externally, mapped to `validate_output` internally (`TriggerExtractionRequest` alias).
- `POST /api/reports/{id}/extract` returns `202` + `Location: /api/jobs/{job_id}`.
- Model IDs are policy-validated in API, worker, CLI, and config load.
- `google-vertex:*` is explicitly rejected; use `google-gla:*`.

## 7) Frontend state (current)

`extractor-ui/`:

- Single Alpine component: `extractorApp()`
- Hash routes: `#/`, `#/reports`, `#/reports/{id}`, `#/reports/{id}/extracting/{job}`, `#/extractions/{id}`
- Mock mode via `?mock` (used by Playwright tests)
- CDN stack: Tailwind v4 browser CDN + Flowbite 4.0.1 + Alpine

`viewer/`:

- Single Alpine component: `iplApp()`
- Static JSON-driven data under `viewer/data/`
- Uses shared popover system and manual positioning math
- Currently still Tailwind v3 Play CDN + Flowbite 4.0.0 + vanilla JS theme-toggle script (known refactor target)

## 8) Useful commands

Backend/dev:

```bash
task lint
task test
task test:smoke
task test:integration
task stack:up
task stack:down
```

Migrations:

```bash
task db:migrate
task db:revision MSG="describe change"
task db:check
task db:stamp:baseline
```

UI tests:

```bash
uv run pytest tests/test_ui.py -v
```

## 9) Testing strategy map

- Core backend unit/component tests: `tests/test_store.py`, `tests/test_api.py`, `tests/test_tasks.py`
- Contract/config/policy tests: `tests/test_config.py`, `tests/test_model_catalog.py`, `tests/test_model_policy.py`
- Migration checks: `tests/test_migrations.py` + `task db:check`
- Extractor UI E2E: `tests/test_ui.py` (mock mode, no backend needed)
- Full integration (Docker + credentials): `tests/test_integration.py` (`-m integration`)
- Project testing conventions: `docs/testing-practices.md`
- Generic pytest guidance skill: `.agents/skills/pytest-testing-patterns/`

## 10) Common gotchas

1. Do not bypass `Taskfile.yml`; it is the intended workflow surface.
2. Keep frontend edits in Alpine + Flowbite patterns; avoid introducing build tooling unless explicitly requested.
3. Treat model/provider behavior as policy-driven (`model_policy.py`) rather than ad hoc checks.
4. Prefer code/tests over plan docs when they conflict.
5. Caddy serves `extractor-ui/` at `/` and proxies `/api/*`; viewer is separate static app.

## 11) If you need to debug quickly

1. Check `/api/readyz` (it verifies both DB and broker backend).
2. Check job row state transitions (`jobs` table) and worker logs.
3. Validate model string against `validate_model_id`.
4. Reproduce with `task test:smoke` before diving into full integration.
5. For extractor UI behavior, reproduce first in `?mock` mode to isolate backend issues.
