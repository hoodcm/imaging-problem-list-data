# Package Restructuring & Cleanup Plan

Last updated: 2026-03-11
Status: Active

## Scope & Assumptions

This is a **breaking cleanup** of a proof-of-concept project. Explicitly:

- Breaking internal, API, and schema renames are in scope where they improve consistency
- No backward-compatibility shims, aliases, or transitional layers
- No legacy database to protect — existing SQLite databases will be dropped and recreated
- All 10 existing Alembic migrations will be collapsed into a single baseline init
- Frontend (`extractor-ui/`), tests, and persistence code will be updated in lockstep
- `docs/pending-refactoring.md` priority labels are superseded — items folded into this cleanup are now active

## Current State (confirmed 2026-03-11)

| Item | Status |
|------|--------|
| `ExamInfo.study_description` | Already standardized in `models.py` |
| `TriggerExtractionRequest.exam_description` | Still uses "exam" in API |
| `ExtractionRow.exam_description_hint` | Still uses "exam" in persistence |
| `ExtractionDetailResponse.exam_description_hint` | Still uses "exam" in API response |
| `Settings` class name | Still `Settings` in `config.py` |
| `ExtractorDeps` | Still in `models.py` |
| `validator_*` config fields | Still `validator_*` throughout |
| `llm_config/` package name | Still `llm_config/` |
| `ReportExtraction`, `ExtractedFinding` etc. | Current names, not yet renamed |
| TaskIQ broker init | Binds to `finding_extractor.api:app` |
| All 25 top-level .py files | Still flat |

## Target Structure

```
src/finding_extractor/
    __init__.py              # Slim re-exports of public API
    models.py                # Core Pydantic models
    coding_summary.py        # 34 lines, cross-cutting (used by db + cli)
    smoke.py                 # Standalone smoke test runner

    core/                    # Foundation: config, base, logging, observability
        __init__.py
        config.py            # ExtractorSettings (renamed from Settings)
        base_model.py        # from base.py
        logging_setup.py
        observability.py

    api/                     # FastAPI layer
        __init__.py          # create_app(), main()
        routes.py
        schemas.py           # request/response models (split from api_models.py)
        mappers.py           # Stored*/domain → API conversion (split from api_models.py)
        services.py
        dependencies.py

    db/                      # Persistence layer (split from store.py)
        __init__.py          # Re-exports ExtractionStore + Stored* types
        tables.py            # SQLModel table classes
        store.py             # ExtractionStore class + Stored* dataclasses

    worker/                  # TaskIQ async processing
        __init__.py
        broker.py
        extraction_jobs.py   # renamed from tasks.py

    cli/                     # CLI entry points
        __init__.py
        extract.py           # from cli.py
        batch.py             # from batch_cli.py (split further in Track 2)
        eval_cmd.py          # from eval_cli.py
        runtime_budget.py

    extractor/               # Extraction pipeline + text processing
        __init__.py
        agent.py             # + ExtractorDeps moved here
        orchestrator.py
        runtime.py
        review.py
        exam_info_agent.py
        prompt.py            # moved from root
        report_sections.py   # moved from root
        chunking.py          # moved from semantic_chunking.py
        impression_chunker.py # moved from impression_list_chunker.py
        verbatim.py          # moved from root

    llm/                     # renamed from llm_config/
    eval/                    # unchanged
    examples/                # unchanged
```

## Domain Vocabulary Standardization

### Rename classification

Each rename is classified by what it affects:

**Internal only** (Python code, no external contract):
| Current | New | Scope |
|---------|-----|-------|
| `ReportExtraction` | `ExtractedReportFindings` | type name |
| `ChunkExtraction` | `ExtractedChunkFindings` | type name |
| `ExtractedFinding` | `Finding` | type name |
| `ExtractionResult.extraction` | `.report_findings` | field name |
| `ChunkExtractionResult.extraction` | `.chunk_findings` | field name |
| `OrchestratedExtractionResult` | `OrchestrationResult` | type name |
| `RuntimeResult` | `PipelineRunResult` | type name |
| `ReportChunk.report_chunk` | `ReportChunk.text` | field name |
| `ExtractorDeps.status_callback` | `.progress_callback` | field name |
| `EmitStatusFn` | `ProgressCallbackFn` | type alias |
| `emit_status()` / `_emit_stage()` | `emit_progress()` / `_emit_stage_progress()` | function names |
| `_resolve_validator_model_name()` | `_resolve_reviewer_model_name()` | function name |
| `extract_chunk_findings as extract_findings` alias | remove alias | import cleanup |
| Legacy `extract_findings()` | remove if unused | dead code |

**API contract** (affects frontend, API consumers):
| Current | New | Notes |
|---------|-----|-------|
| `TriggerExtractionRequest.exam_description` | `.study_description` | Request field |
| `ExtractionDetailResponse.exam_description_hint` | `.study_description_hint` | Response field |
| `ExtractionSummaryResponse` field names with `coding_coded_count` | `coded_finding_count` | Response field |
| `ExtractionSummaryResponse` field names with `coding_unresolved_count` | `unresolved_finding_count` | Response field |

**Persistence/schema** (requires Alembic migration):
| Current | New | Notes |
|---------|-----|-------|
| `ExtractionRow.exam_description_hint` | `.study_description_hint` | Column rename |
| `ExtractionRow.coding_coded_count` | `.coded_finding_count` | Column rename |
| `ExtractionRow.coding_unresolved_count` | `.unresolved_finding_count` | Column rename |

**Config** (affects env vars, config.toml):
| Current | New | Notes |
|---------|-----|-------|
| `Settings` | `ExtractorSettings` | Class name only; `IPL_*` env prefix unchanged |
| `validator_review_enabled` | `reviewer_enabled` | Config field + env var |
| `validator_model` | `reviewer_model` | Config field + env var |
| `validator_reasoning` | `reviewer_reasoning` | Config field + env var |
| `validator_reextract_enabled` | `reviewer_reextract_enabled` | Config field + env var |

**Diagnostics** (affects pipeline_diagnostics JSON in DB):
| Current | New |
|---------|-----|
| `validator_requested_chunks` | `reviewer_requested_chunks` |
| `validator_reextracted_chunks` | `reviewer_reextracted_chunks` |

### Pipeline data flow with new names

```
report_text (str)
  ↓ parse_report_sections()
ParsedReport.sections: list[ReportSection]
  ↓ _build_section_chunks()
list[ReportChunk]  (.text = chunk text)
  ↓ semantic chunking
expanded list[ReportChunk]
  ↓ extract_chunk_findings() per chunk
ChunkExtractionResult (.chunk_findings: ExtractedChunkFindings)
  ↓ merge + dedupe
ExtractedReportFindings (.findings: list[Finding])
  ↓ reviewer (optional)
ExtractionReviewDecision
  ↓ validate
ValidationResult
  ↓ persist
ExtractionRow (extraction_json)
  ↓ read back
StoredExtractionDetail (.extraction: ExtractedReportFindings)
  ↓ API mapper
ExtractionDetailResponse
```

## Branch Strategy

Before any code changes:

```bash
git checkout dev
git checkout -b refactor/package-restructuring
```

All work happens on `refactor/package-restructuring`. Each phase below is one commit.

## Workflow Per Phase

Every phase follows this pattern:

1. Make the code changes described
2. Update any docs that reference moved/renamed modules (inline with the phase, not deferred)
3. Append a concise entry to `docs/DEV_LOG.md` summarizing what changed in this phase
4. `task lint && task test`
5. Commit with the message shown (messages are brief because DEV_LOG has the detail)

---

## Execution Tracks

Work is organized into 3 tracks executed sequentially. Each phase is one commit.

---

### Track 1: Package & module structure (mechanical moves)

#### 1a: Create `core/` subpackage
- Create `core/__init__.py`
- Move `config.py` → `core/config.py`
- Move `base.py` → `core/base_model.py`
- Move `logging_setup.py` → `core/logging_setup.py`
- Move `observability.py` → `core/observability.py`
- Update all imports (17+ modules import config)
- **Docs**: Update `CLAUDE.md` structure section to show `core/` subpackage

**DEV_LOG entry**: "Created `core/` subpackage. Moved `config.py`, `base.py` (→ `base_model.py`), `logging_setup.py`, `observability.py` into `core/`. Updated all imports."

**Commit**: `git commit -m "refactor: create core/ subpackage (see DEV_LOG)"`

#### 1b: Create `api/` subpackage
- Create `api/__init__.py` with app factory + `main()` from `api.py`
- Move `api_routes.py` → `api/routes.py`
- Move `api_models.py` → `api/schemas.py` (mappers split deferred to Track 2)
- Move `api_services.py` → `api/services.py`
- Move `api_dependencies.py` → `api/dependencies.py`
- Update `pyproject.toml`: `finding-extractor-api = "finding_extractor.api:main"`
- **Docs**: Update `CLAUDE.md` structure section for `api/`

**DEV_LOG entry**: "Created `api/` subpackage. Moved `api.py` (→ `api/__init__.py`), `api_routes.py` (→ `routes.py`), `api_models.py` (→ `schemas.py`), `api_services.py` (→ `services.py`), `api_dependencies.py` (→ `dependencies.py`). Updated `pyproject.toml` entry point."

**Commit**: `git commit -m "refactor: create api/ subpackage (see DEV_LOG)"`

#### 1c: Create `worker/` and `cli/` subpackages
- **worker/**: `broker.py` → `worker/broker.py`, `tasks.py` → `worker/extraction_jobs.py`
  - Update `docker-compose.yml` worker command
  - Update TaskIQ FastAPI init string
- **cli/**: `cli.py` → `cli/extract.py`, `batch_cli.py` → `cli/batch.py`, `eval_cli.py` → `cli/eval_cmd.py`, `runtime_budget.py` → `cli/runtime_budget.py`
  - Update `pyproject.toml` entry points
- **Docs**: Update `CLAUDE.md` structure section for `worker/` and `cli/`

**DEV_LOG entry**: "Created `worker/` subpackage (`broker.py`, `tasks.py` → `extraction_jobs.py`) and `cli/` subpackage (`cli.py` → `extract.py`, `batch_cli.py` → `batch.py`, `eval_cli.py` → `eval_cmd.py`, `runtime_budget.py`). Updated `docker-compose.yml` and `pyproject.toml` entry points."

**Commit**: `git commit -m "refactor: create worker/ and cli/ subpackages (see DEV_LOG)"`

#### 1d: Create `db/` subpackage + move text processing into `extractor/`
- **db/**: Move `store.py` → `db/store.py` (no split yet — that's Track 2)
  - Create `db/__init__.py` with re-exports
  - Update `alembic/env.py`
- **extractor text processing**: Move `report_sections.py`, `semantic_chunking.py` → `chunking.py`, `impression_list_chunker.py` → `impression_chunker.py`, `prompt.py`, `verbatim.py` into `extractor/`
- **Docs**: Update `CLAUDE.md` structure section for `db/` and `extractor/` changes

**DEV_LOG entry**: "Created `db/` subpackage (moved `store.py`; updated `alembic/env.py`). Moved text-processing modules into `extractor/`: `report_sections.py`, `semantic_chunking.py` (→ `chunking.py`), `impression_list_chunker.py` (→ `impression_chunker.py`), `prompt.py`, `verbatim.py`."

**Commit**: `git commit -m "refactor: create db/ subpackage, consolidate extractor/ (see DEV_LOG)"`

#### 1e: Rename `llm_config/` → `llm/`
- Rename package directory
- Rename `llm/providers.py` → `llm/model_settings.py`
- Update all imports
- **Docs**: Update `CLAUDE.md` structure section for `llm/`

**DEV_LOG entry**: "Renamed `llm_config/` → `llm/`. Renamed `providers.py` → `model_settings.py`. Updated all imports."

**Commit**: `git commit -m "refactor: rename llm_config/ to llm/ (see DEV_LOG)"`

---

### Track 2: Oversized file decomposition

#### 2a: Split `db/store.py` (917 lines)
- Extract table classes (`ReportRow`, `ExtractionRow`, `CorrectionRow`, `JobRow`, `UserRow`) → `db/tables.py`
- Keep `ExtractionStore` + `Stored*` dataclasses in `db/store.py`
- Update `alembic/env.py`: `from finding_extractor.db import tables as _tables` (Alembic reset comes later in 3c)

**DEV_LOG entry**: "Split `db/store.py`: extracted SQLModel table classes to `db/tables.py`. Store facade and `Stored*` dataclasses remain in `db/store.py`."

**Commit**: `git commit -m "refactor: split db/store.py, extract tables (see DEV_LOG)"`

#### 2b: Split `api/schemas.py` → `schemas.py` + `mappers.py`
- Extract 8 `map_*` functions → `api/mappers.py` (~150 lines)
- Keep request/response Pydantic models in `api/schemas.py` (~290 lines)

**DEV_LOG entry**: "Split `api/schemas.py`: extracted `map_*` conversion functions to `api/mappers.py`. Request/response models stay in `schemas.py`."

**Commit**: `git commit -m "refactor: split api/schemas.py, extract mappers (see DEV_LOG)"`

#### 2c: Split `cli/batch.py` (923 lines)
- `cli/batch.py` — Click command entrypoints + CLI argument parsing
- `cli/batch_engine.py` — run engine, file processing, preflight checks
- `cli/batch_state.py` — run-state directory/JSON helpers, status tracking

**DEV_LOG entry**: "Split `cli/batch.py` (923→~3 files): CLI entrypoints stay in `batch.py`, run engine to `batch_engine.py`, state/directory helpers to `batch_state.py`."

**Commit**: `git commit -m "refactor: split cli/batch.py into engine + state (see DEV_LOG)"`

---

### Track 3: Naming cleanup

#### 3a: Internal-only type and function renames
No API, persistence, or config changes. Safe to rename freely.

- `ReportExtraction` → `ExtractedReportFindings`
- `ChunkExtraction` → `ExtractedChunkFindings`
- `ExtractedFinding` → `Finding`
- `ExtractionResult.extraction` → `.report_findings`
- `ChunkExtractionResult.extraction` → `.chunk_findings`
- `OrchestratedExtractionResult` → `OrchestrationResult`
- `RuntimeResult` → `PipelineRunResult`
- `ReportChunk.report_chunk` → `ReportChunk.text`
- `ExtractorDeps.status_callback` → `.progress_callback`
- `EmitStatusFn` → `ProgressCallbackFn`
- `emit_status()` → `emit_progress()`, `_emit_stage()` → `_emit_stage_progress()`
- Remove `extract_chunk_findings as extract_findings` alias
- Remove legacy `extract_findings()` if unused
- Move `ExtractorDeps` from `models.py` to `extractor/agent.py` (PR-014)
- `Settings` → `ExtractorSettings` (class name only; env prefix unchanged)

**DEV_LOG entry**: "Internal naming cleanup: `ReportExtraction` → `ExtractedReportFindings`, `ExtractedFinding` → `Finding`, `ChunkExtraction` → `ExtractedChunkFindings`. Renamed result fields, callback types, and emit helpers for pipeline clarity. Moved `ExtractorDeps` to `extractor/agent.py`. Renamed `Settings` → `ExtractorSettings`."

**Commit**: `git commit -m "refactor: internal type/function naming cleanup (see DEV_LOG)"`

#### 3b: Config field renames (reviewer standardization)
Changes env var names — requires config.toml.example and docs update.

- `validator_review_enabled` → `reviewer_enabled`
- `validator_model` → `reviewer_model`
- `validator_reasoning` → `reviewer_reasoning`
- `validator_reextract_enabled` → `reviewer_reextract_enabled`
- `_resolve_validator_model_name()` → `_resolve_reviewer_model_name()`
- `PipelineDiagnostics.validator_requested_chunks` → `.reviewer_requested_chunks`
- `PipelineDiagnostics.validator_reextracted_chunks` → `.reviewer_reextracted_chunks`
- **Docs**: Update `config.toml.example`, `docs/configuration.md`

**DEV_LOG entry**: "Standardized reviewer vocabulary: renamed `validator_*` config fields/env vars to `reviewer_*`. Updated `PipelineDiagnostics` fields. Updated `config.toml.example` and `docs/configuration.md`."

**Commit**: `git commit -m "refactor: rename validator_* to reviewer_* (see DEV_LOG)"`

#### 3c: API contract + persistence renames + Alembic reset
Breaking changes to API and database schema. No migration needed — we collapse all Alembic history.

- `TriggerExtractionRequest.exam_description` → `.study_description`
- `ExtractionDetailResponse.exam_description_hint` → `.study_description_hint`
- `ExtractionRow.exam_description_hint` → `.study_description_hint`
- `ExtractionRow.coding_coded_count` → `.coded_finding_count`
- `ExtractionRow.coding_unresolved_count` → `.unresolved_finding_count`
- `exam_name` in review.py prompts → `study_description`

**Alembic reset:**
- Delete all 10 files in `alembic/versions/`
- Generate a single new baseline migration from current table definitions: `uv run alembic revision --autogenerate -m "baseline_schema"`
- Verify: `rm -f *.db && uv run alembic upgrade head`

**Additional tasks:**
- Update `extractor-ui/app.js` for changed API field names
- Update API test fixtures/assertions

**DEV_LOG entry**: "API/persistence naming cleanup: `exam_description` → `study_description`, `exam_description_hint` → `study_description_hint`, `coding_coded_count` → `coded_finding_count`, `coding_unresolved_count` → `unresolved_finding_count`. Collapsed all 10 Alembic migrations into single baseline. Updated `extractor-ui/app.js` and test fixtures."

**Commit**: `git commit -m "refactor: API + persistence renames, reset Alembic baseline (see DEV_LOG)"`

---

### Track 4: Backlog cleanups (independent of restructuring)

These touch the same code but are behavior changes, not renames. Each is a separate commit.

- PR-006: Simplify/remove `ValidationResult.is_valid` if redundant
- PR-008: Unify logging style (structlog everywhere)
- PR-001/002: Replace broad `Callable[..., ...]` with `Protocol` for progress callbacks
- PR-004: De-duplicate review-callback wiring in `extractor/runtime.py` vs `worker/extraction_jobs.py`

Each gets its own DEV_LOG entry and commit message referencing the PR ID, e.g.:
- `git commit -m "cleanup: simplify ValidationResult.is_valid (PR-006, see DEV_LOG)"`
- `git commit -m "cleanup: unify structlog usage (PR-008, see DEV_LOG)"`
- `git commit -m "cleanup: typed Protocol for callbacks (PR-001/002, see DEV_LOG)"`
- `git commit -m "cleanup: de-dup review-callback wiring (PR-004, see DEV_LOG)"`

---

### Final: Update docs + mark backlog complete

- Update `CLAUDE.md` repository structure section (final pass — catch anything missed)
- Update `docs/pending-refactoring.md` — mark completed items, remove resolved PRs
- Update any remaining docs referencing old module paths
- Full verification: `task lint && task test && task stack:up`
- Verify fresh DB: `rm -f *.db && uv run alembic upgrade head`

**DEV_LOG entry**: "Final docs pass: updated `CLAUDE.md` structure, marked completed items in `pending-refactoring.md`."

**Commit**: `git commit -m "docs: finalize restructuring docs and close backlog items (see DEV_LOG)"`

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| Text processing → `extractor/` | Only consumed by extractor modules (+ one db import). Extraction-specific, not generic. |
| `core/` for config + base + logging + observability | Standard FastAPI pattern. Groups foundational infrastructure. |
| `db/` package name | PR-013 says `store.py → persistence.py/db.py`. `db/` is standard. |
| `coding_summary.py` stays top-level | Imported by both cli and store. Moving to cli creates wrong dependency direction. |
| App factory in `api/__init__.py` | Keeps `"finding_extractor.api:create_app"` as the import string. |
| `cli/eval_cmd.py` not `cli/eval.py` | Avoids shadowing Python's `eval` builtin. |
| Keep `finding_extractor` package name | Renaming to `ipl_backend` is massive churn for marginal benefit. |

## What NOT to do

- Don't split `models.py` (345 lines, tightly cohesive)
- Don't split `config.py` (577 lines, one cohesive Settings class)
- Don't create a `utils/` grab-bag
- Don't reorganize `eval/` or `examples/` internals
- Don't split routes into per-resource routers (203 lines total)
- Don't restructure test directory into subfolders
- Don't add backward-compat shims or import aliases

## Integration points

| Reference | Location | New value |
|-----------|----------|-----------|
| `finding-extractor` CLI | `pyproject.toml` | `finding_extractor.cli.extract:main` |
| `finding-extractor-api` CLI | `pyproject.toml` | `finding_extractor.api:main` |
| `finding-extractor-batch` CLI | `pyproject.toml` | `finding_extractor.cli.batch:cli` |
| `finding-extractor-eval` CLI | `pyproject.toml` | `finding_extractor.cli.eval_cmd:cli` |
| TaskIQ worker | `docker-compose.yml` | `finding_extractor.worker.broker:broker finding_extractor.worker.extraction_jobs` |
| Alembic metadata | `alembic/env.py` | `from finding_extractor.db import tables as _tables` |
| TaskIQ FastAPI init | `worker/broker.py` | `"finding_extractor.api:create_app"` |

## Verification (after each commit)

```bash
task lint && task test
```

After final phase:
```bash
task lint && task test && task stack:up
rm -f *.db && uv run alembic upgrade head
uv run finding-extractor --help
# grep for stale imports:
grep -r 'finding_extractor\.store\b\|finding_extractor\.config\b\|finding_extractor\.api_\|finding_extractor\.broker\b\|finding_extractor\.tasks\b\|finding_extractor\.batch_cli\|finding_extractor\.eval_cli\|finding_extractor\.logging_setup\b\|finding_extractor\.observability\b\|finding_extractor\.base\b\|finding_extractor\.report_sections\b\|finding_extractor\.semantic_chunking\b\|finding_extractor\.impression_list\b\|finding_extractor\.prompt\b\|finding_extractor\.verbatim\b\|finding_extractor\.llm_config\b' src/ tests/
```
