# Dev Log

## 2026-02-10 — Extractor UI CDN alignment + skill documentation cleanup

Aligned `extractor-ui/index.html` and `extractor-ui/app.js` with the project's Flowbite/Tailwind/Alpine CDN stack, and comprehensively fixed all skill reference docs.

### Extractor UI changes (Phase 1–2 of refactoring plan)
- **CDN stack**: Replaced Tailwind v3 Play CDN (`cdn.tailwindcss.com`) with Flowbite CSS 4.0.1 + Tailwind v4 browser CDN (`@tailwindcss/browser@4`) + `@custom-variant dark` for class-based dark mode. Flowbite CSS loads first (includes a complete Tailwind v4 build), then the browser CDN adds dynamic utility generation and class-based dark mode.
- **Flowbite 4.0.0 → 4.0.1**: Updated both CSS and JS CDN references.
- **FOUC script**: Changed from system-preference-based to dark-by-default (`localStorage 'light'` opts out).
- **Dark mode toggle**: Renamed `isDark` → `darkMode`, added `$watch` reactive pattern, removed imperative `toggleDarkMode()` method, updated HTML to `@click="darkMode = !darkMode"` with `x-show` on SVG icons.
- **Semantic token migration rejected**: Flowbite v4 semantic tokens (`text-heading`, `bg-brand`, etc.) require a build step; they resolve to nothing in CDN-only setups. Sticking with classic `dark:` prefix approach.

### Skill documentation overhaul
- **`SKILL.md`**: Corrected version matrix, CDN stack (Tailwind v4, not v3), anti-patterns, and added explanatory note that Flowbite CSS includes a complete Tailwind v4 build.
- **`references/component-templates.md`**: Rewrote all 21 component template sections to use classic `dark:` prefix classes instead of semantic tokens. Every template is now copy-paste ready for CDN-only projects.
- **`references/alpine-patterns.md`**: Fixed ~20 code examples that used semantic tokens (forms, badges, cards, buttons, nested components, star ratings, modals).
- **`references/color-patterns.md`**: Corrected CDN setup section (Tailwind v4, not v3), removed stale "Why not Tailwind v4?" callout. Semantic token mapping table preserved as future reference.

### Planning docs
- **`docs/extractor-ui-refactoring.md`**: Rewritten to reflect completed state (phases 1–2 done, semantic tokens rejected with rationale).
- **`docs/viewer-refactoring.md`**: New detailed plan for aligning the IPL viewer with the same CDN stack (5 concrete items with before/after code, recommended order, verification steps).

### Cleanup
- Deleted 12 test-artifact screenshot PNGs from repo root.

**Verification:** All 48 Playwright tests pass (`uv run pytest tests/test_ui.py -v`).

## 2026-02-10 — Data-model Track A started (strict model base + shared aliases)

Started data-model consolidation Track A with low-risk steps that do not change schema or API
contracts.

- Added `src/finding_extractor/base.py` with `StrictBaseModel` (`extra="forbid"`).
- Updated `src/finding_extractor/models.py` to inherit from `StrictBaseModel` and introduced
  shared aliases:
  - `CorrectionType`
  - `CorrectionStatus`
  - `JobStatus`
  - `Presence`
- Updated API request/response models in `src/finding_extractor/api.py` to inherit from
  `StrictBaseModel`.
- Updated `src/finding_extractor/store.py` to import shared aliases from `models.py` and build
  SQL `CHECK` constraints from those aliases to keep Python/DB status values aligned.
- Reduced API endpoint boilerplate in `src/finding_extractor/api.py` by centralizing repeated
  store->response mapping in helper functions (no response contract changes).
- Validation:
  - `task lint` passed
  - `task test:unit` passed

## 2026-02-10 — Config plan doc cleanup + schema migration runbook

Cleaned up planning docs to match implemented config behavior and added an explicit
schema-migration runbook for future contributors/agents.

- `docs/config-plan.md` now reflects the actual flat `Settings` implementation and real
  changed files.
- Added `docs/schema-migrations.md` with first-time DB adoption, schema-change workflow,
  and required PR checklist commands.
- Added cross-links in:
  - `README.md`
  - `docs/dev-ops.md`
  - `docs/persistence-internals.md`
  - `docs/migration-architecture.md`

## 2026-02-10 — Env-first config centralization (Phase 1/2)

Implemented centralized runtime settings using `pydantic-settings` and removed ad-hoc env
resolution from backend runtime modules.

- Added `src/finding_extractor/config.py`:
  - `Settings` with env-first defaults and compatibility aliases for existing env names.
  - cached `get_settings()` and `clear_settings_cache()` helper.
- Wired settings usage in:
  - `src/finding_extractor/agent.py`
  - `src/finding_extractor/api.py`
  - `src/finding_extractor/cli.py`
  - `src/finding_extractor/tasks.py`
  - `src/finding_extractor/broker.py`
- Added config regression coverage:
  - `tests/test_config.py`
  - `tests/conftest.py` cache-clear fixture for deterministic env tests.
- Updated workflow/docs:
  - `Taskfile.yml` (`test:unit` now includes `tests/test_config.py`)
  - `README.md`
  - `docs/config-plan.md`
  - `docs/data-model-plan.md`
  - `docs/api-server.md`
## 2026-02-10 — Alembic migration foundation implemented

Implemented the migration foundation so schema evolution no longer depends on `create_all`.

- Added Alembic scaffolding:
  - `alembic.ini`
  - `alembic/env.py`
  - `alembic/script.py.mako`
  - `alembic/versions/17f8ebc6c608_baseline_schema.py`
- Wired Alembic metadata/autogenerate to SQLModel tables and SQLite-safe batch mode.
- Added migration task commands in `Taskfile.yml`:
  - `db:migrate`, `db:migrate:stack`, `db:stamp:baseline`, `db:stamp:baseline:stack`, `db:revision`, `db:current`, `db:heads`, `db:check`
- Updated container packaging for migration support:
  - `Dockerfile` now includes `alembic/` and `alembic.ini` in the image.
- Added migration regression tests:
  - `tests/test_migrations.py`
  - Includes pre-Alembic adoption coverage (`create_all` schema -> `stamp` baseline -> `upgrade head`)
- Updated docs to reflect current policy and commands:
  - `docs/migration-architecture.md`
  - `docs/persistence-internals.md`
  - `docs/api-server.md`
  - `docs/dev-ops.md`
  - `README.md`
## 2026-02-10 — Readiness contract tightened for queue-backed extraction

Updated API readiness behavior so `/api/readyz` now checks extraction dependencies, not just DB reachability.

- Added broker-backend readiness check in `src/finding_extractor/api.py`:
  - `assert_broker_ready(...)` pings Redis through TaskIQ broker connection pool when available.
  - non-Redis test brokers (e.g. `InMemoryBroker`) are treated as ready to keep deterministic unit tests.
- Updated `/api/readyz` to return `503 Not ready` if either:
  - database access check fails, or
  - broker backend connectivity check fails.
- Added regression test in `tests/test_api.py`:
  - `test_readyz_returns_503_when_broker_backend_is_unavailable`.
- Updated docs for readiness semantics:
  - `docs/api-server.md`
  - `docs/api-internals.md`
  - `docs/api-usage.md`
  - `docs/dev-ops.md`

## 2026-02-10 — Correction target validation hardening

Hardened correction persistence so `update_finding` corrections cannot be stored without a resolvable target finding path.

- `src/finding_extractor/store.py` now rejects out-of-range `target_finding_index` for `update_finding` with:
  - `ValueError("update_finding target_finding_index does not exist in extraction findings")`
- API behavior remains contract-stable:
  - `src/finding_extractor/api.py` maps store `ValueError` to `422`
- Added regression coverage:
  - `tests/test_store.py` verifies invalid index raises and no correction row is persisted.
  - `tests/test_api.py` verifies invalid index returns `422` and correction list remains empty.
- Updated validation docs:
  - `docs/persistence-internals.md`
  - `docs/api-internals.md`
  - `docs/api-usage.md`
- Frontend impact:
  - No immediate UI code change required because current MVP UI only creates `comment` corrections (no `update_finding` form yet).
## 2026-02-09 — Lean backend workflow + integration hardening

Aligned backend workflow to a lean strategy while merging in full-stack integration improvements.

- Added `Taskfile.yml` as the primary workflow surface:
  - `lint` (ruff + ty)
  - `test` / `test:unit`
  - `test:smoke`
  - `test:integration`
  - `stack:up` / `stack:up:full` / `stack:down`
- Moved smoke-test logic to Python module:
  - `src/finding_extractor/smoke.py`
- Removed shell smoke wrapper (`scripts/smoke_api.sh`) to keep deep logic out of shell.
- Added full-stack integration assets from `dev` branch:
  - `Caddyfile` reverse proxy and Compose `caddy` service
  - Docker healthchecks and `service_healthy` startup ordering
  - `tests/test_integration.py` for browser -> proxy -> API -> worker -> Redis coverage
- Added explicit API health endpoints for operational probes:
  - `GET /api/healthz` (liveness)
  - `GET /api/readyz` (readiness)
- Completed targeted typing cleanup to keep strict `ty` checks viable:
  - Typed Anthropic thinking settings in `src/finding_extractor/agent.py`.
  - Tightened validation-result typing in `src/finding_extractor/cli.py`.
  - Used SQLModel `col(...).desc()` expressions in `src/finding_extractor/store.py`.
  - Added targeted test typing adjustments in `tests/test_extraction.py`, `tests/test_models.py`, and `tests/test_store.py`.
  - Kept canonical FastAPI CORS middleware usage with a narrowly scoped `ty` suppression in `src/finding_extractor/api.py`.

Scope decision:
- Keep default focus on unit/component + smoke.
- Keep full-stack integration tests optional and out of the default fast path.

## 2026-02-08 — Extraction frontend MVP

Built a zero-build static frontend for the extraction API using Alpine.js 3.x, Tailwind CSS, and Flowbite 4.0 (all via CDN). The SPA (`extractor-ui/index.html` + `extractor-ui/app.js`) implements the full MVP workflow: submit report, trigger extraction with optional model/reasoning overrides, poll job progress, view structured extraction results (findings with presence/location/attribute badges, non-finding text, validation), and add comment corrections. Hash routing drives five views; a `?mock` URL parameter activates an in-memory mock API layer for offline development. The frontend was validated against the running backend's OpenAPI schema, including response flattening for the nested `ExtractionDetailResponse` shape. 48 Playwright E2E tests (`tests/test_ui.py`) cover all views, routing, dark mode, and end-to-end flows. Static files are served by Caddy reverse proxy in production (see 2026-02-09 entry).

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
