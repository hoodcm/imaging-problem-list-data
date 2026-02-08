# Dev Log

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
