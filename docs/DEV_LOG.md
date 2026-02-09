# Dev Log

## 2026-02-08 — Frontend + backend integration via Caddy reverse proxy

Added a Caddy reverse proxy to Docker Compose to serve the extraction frontend and proxy `/api/*` to the FastAPI backend. The `Caddyfile` at the repo root serves `extractor-ui/` at `/` and forwards API requests to the `api` service. The frontend is now accessible at `http://localhost:8080` after `docker compose up`. Redis port exposure was removed (internal-only). The smoke test (`scripts/smoke_api.sh`) passes end-to-end through the proxy.

**Files:** `Caddyfile` (new), `docker-compose.yml`, `.dockerignore`, `docs/extractor-frontend.md`, `docs/dev-ops.md`, `docs/frontend-usage.md`.

## 2026-02-08 — Extraction frontend MVP

Built a zero-build static frontend for the extraction API using Alpine.js 3.x, Tailwind CSS, and Flowbite 4.0 (all via CDN). The SPA (`extractor-ui/index.html` + `extractor-ui/app.js`) implements the full MVP workflow: submit report, trigger extraction with optional model/reasoning overrides, poll job progress, view structured extraction results (findings with presence/location/attribute badges, non-finding text, validation), and add comment corrections. Hash routing drives five views; a `?mock` URL parameter activates an in-memory mock API layer for offline development. The frontend was validated against the running backend's OpenAPI schema, including response flattening for the nested `ExtractionDetailResponse` shape. 48 Playwright E2E tests (`tests/test_ui.py`) cover all views, routing, dark mode, and end-to-end flows. Static files are served by Caddy reverse proxy in production (see Caddy integration entry above).

**Docs:** [`docs/extractor-frontend.md`](extractor-frontend.md) (plan + implementation status), [`docs/frontend-usage.md`](frontend-usage.md) (user guide with screenshots), [`docs/frontend-internals.md`](frontend-internals.md) (developer/agent reference).

## 2026-02-08 — FastAPI + TaskIQ API server MVP stabilization

Implemented and stabilized the API-server plan with a FastAPI HTTP surface, TaskIQ worker pipeline, and Dockerized local runtime:

- Added API layer and routes in `src/finding_extractor/api.py` (reports, extraction dispatch/status, extraction detail/list, corrections).
- Added broker/task modules in `src/finding_extractor/broker.py` and `src/finding_extractor/tasks.py`.
- Extended persistence in `src/finding_extractor/store.py` with:
  - SQLite WAL pragmas on connect
  - read APIs for reports/extractions
  - async `jobs` table lifecycle methods for polling semantics
- Added tests for API/store behavior and task error handling:
  - `tests/test_api.py`
  - `tests/test_store.py` updates
  - `tests/test_tasks.py`
- Added container/runtime artifacts:
  - `Dockerfile`
  - `docker-compose.yml`
  - `.dockerignore`
  - `scripts/smoke_api.sh`

Security hardening in this pass:

- Job failure payloads were sanitized to stable public error codes.
- Enqueue failures now persist as `enqueue_failed:queue_unavailable`.
- Worker failures now persist as `extraction_failed:*` without leaking raw exception text.
- Internal exception details remain in server logs.

Docs updated/added in this pass:

- Updated in-place plan/status doc: `docs/api-server.md`
- Updated persistence docs: `docs/persistence-usage.md`, `docs/persistence-internals.md`
- New docs:
  - `docs/api-usage.md`
  - `docs/api-internals.md`
  - `docs/dev-ops.md`
## 2026-02-08 — CLI persistence integration

Reintroduced optional persistence wiring in `finding-extractor` CLI using the existing async store API (`ExtractionStore`) instead of custom storage code. CLI now supports `--store/--no-store` and `--db-path`, writes `reports` + `extractions` when enabled, and includes run metadata in output (`_storage` for JSON and `PERSISTENCE` block for table format). The implementation uses a single async orchestration function bridged once with `asyncer.runnify(...)` at the CLI boundary.

Added CLI coverage for persistence behavior in `tests/test_cli.py`, including row creation and `_storage` metadata assertions.

## 2026-02-08 — Multi-provider model support (`957274e`)

The extraction agent was hardcoded to OpenAI. We refactored `agent.py` to detect the provider from the pydantic-ai model string prefix and dispatch to per-provider settings builders, so the same `--reasoning` flag now maps to OpenAI reasoning effort, Anthropic extended thinking, and Google thinking levels. Ollama is supported but has no thinking mechanism. This required no new dependencies — pydantic-ai already bundles all provider settings types. We also added `"none"` as a valid reasoning level in the CLI. Known issue: `--reasoning none` doesn't actually override agent-level defaults for OpenAI/Google due to a `None`-overloading problem in `extract_findings()`; tracked in `docs/extraction-internals.md` along with other follow-up items.

**Docs:** [`docs/extraction-usage.md`](extraction-usage.md) (user guide), [`docs/extraction-internals.md`](extraction-internals.md) (contributor guide with known issues and future work).

## 2026-02-08 — Async persistence layer + CLI deferral plan

Added a dedicated async persistence layer in `src/finding_extractor/store.py` using SQLModel + SQLAlchemy async (`sqlite+aiosqlite`). The schema now centers on three entities: `reports` (dedup by `text_hash`), `extractions` (run-level metadata + full JSON payload), and `corrections` (human feedback records with type/status and optional finding targeting). Persistence tests were added in `tests/test_store.py` using native `pytest-asyncio` async fixtures/tests.

We intentionally did **not** wire persistence into `finding-extractor` CLI in this change to keep scope clean and avoid mixing concerns with the already-committed agent/provider work. Instead, we documented a concrete integration plan in `docs/archive/persistence-cli-plan.md` (flags, output shape, async boundary pattern, test plan, rollout order).

Dependencies added in `pyproject.toml` / `uv.lock`:
- `sqlmodel`
- `sqlalchemy[asyncio]`
- `aiosqlite`

**Docs:** [`docs/persistence-usage.md`](persistence-usage.md), [`docs/persistence-internals.md`](persistence-internals.md), [`docs/archive/persistence-cli-plan.md`](archive/persistence-cli-plan.md), [`docs/database-layer.md`](database-layer.md).
