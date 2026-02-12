# Testing Plan

**Status:** Active follow-up plan (post-Stage 3 logging work)
**Execution State (February 12, 2026):**
- `Slice 1` completed.
- `Slice 2` is next.

## Purpose

Improve test maintainability and consistency by reducing fixture duplication, standardizing pytest patterns, and documenting expected testing conventions for contributors and agents.

## Goals

- Consolidate truly shared fixtures into `tests/conftest.py`.
- Keep module-specific fixtures local when they improve readability.
- Reduce ad hoc test helper patterns that are brittle across pytest import modes.
- Publish clear, practical testing guidance for day-to-day development.

## Non-Goals

- No broad test rewrites that change behavior.
- No migration to a different test framework.
- No forced fixture abstraction when usage is single-module or low value.

## Guiding Rules

- Prefer pytest-native fixture sharing via `tests/conftest.py` over ad hoc imports from test modules.
- Only promote fixtures to shared scope when they are reused by 2+ modules or represent global behavior.
- Keep domain-specific setup local when moving it to shared fixtures would hide test intent.
- Use small, reversible PR slices with green checks at every step.

## Current Snapshot

- Shared fixtures now exist for:
  - settings cache reset (`tests/conftest.py`)
  - structured log context capture (`tests/conftest.py`)
  - shared CLI runner (`tests/conftest.py`)
- Remaining opportunities from audit:
  - repeated async `ExtractionStore` setup/teardown patterns
  - repeated runtime logging monkeypatch setup patterns

## Prioritized Workstreams

### Workstream A: Shared Fixtures (low-risk first)

1. `DONE` — Add `cli_runner` fixture in `tests/conftest.py` and migrate:
   - `tests/test_cli.py`
   - `tests/test_batch_cli.py`
   - `tests/test_eval_cli.py`
2. `NEXT` — Add `store_factory` fixture in `tests/conftest.py`:
   - returns an async context manager/factory for `ExtractionStore`.
   - local wrappers may remain for filename clarity (`api.sqlite3`, `tasks.sqlite3`, etc.).
3. Add runtime logging patch helper fixture in `tests/conftest.py`:
   - captures `configure_logfire(...)` and `setup_logging(...)` calls.
   - usable by API/CLI/batch/eval/worker startup tests.
4. Keep behavior assertions unchanged in all fixture-migration slices.

### Workstream B: Documentation (required)

1. Create `docs/testing-patterns.md` as the canonical testing style guide.
2. Document all shared fixtures from `tests/conftest.py`:
   - name
   - scope
   - inputs/returns
   - expected usage
   - example snippet
3. Document expected patterns by test type:
   - pure unit tests
   - async store tests
   - API tests (`ASGITransport`, lifespan)
   - CLI tests (`CliRunner`, `isolated_filesystem`)
   - logging/context tests
4. Document anti-patterns:
   - importing helpers via `tests.*` paths
   - one-off fixtures moved global with no reuse
   - hidden side effects in autouse fixtures
5. Add a lightweight update policy:
   - any new shared fixture must be added to `docs/testing-patterns.md`.
   - any removed fixture must be removed from the catalog.

### Workstream C: Incremental Adoption

1. Apply patterns incrementally during normal feature work.
2. Keep change sets small and test-focused.
3. Validate each slice with:
   - `task lint`
   - `task test`

## Fixture Design Targets

### Candidate Shared Fixtures

- `cli_runner`:
  - scope: function
  - returns: `CliRunner`
  - primary users: CLI/batch/eval CLI tests
- `store_factory`:
  - scope: function
  - returns: async callable/context helper producing initialized `ExtractionStore`
  - primary users: store/api/tasks tests
- `runtime_logging_spy` (name TBD):
  - scope: function
  - returns: mutable call-capture object
  - helpers:
    - patch target module path
    - assert runtime and `include_logfire_processor`

### Keep Local (Do Not Promote Yet)

- API-specific `app` and `client` fixtures in API tests.
- UI/browser server fixtures in UI/integration tests.
- highly test-specific fake pipeline builders.

## Execution Slices (PR-friendly)

### Slice 1: CLI runner standardization

Status: `Completed`

1. Add `cli_runner` fixture.
2. Replace direct `CliRunner()` calls in:
   - `tests/test_cli.py`
   - `tests/test_batch_cli.py`
   - `tests/test_eval_cli.py`
3. Verify no behavior changes.

### Slice 2: Store fixture standardization

Status: `Pending`

1. Introduce `store_factory` fixture.
2. Migrate duplicated `ExtractionStore` setup/teardown in:
   - `tests/test_store.py`
   - `tests/test_api.py`
   - `tests/test_tasks.py`
3. Keep local readability by preserving per-module DB naming wrappers where useful.

### Slice 3: Runtime logging patch helper

Status: `Pending`

1. Add shared logging patch helper fixture.
2. Migrate repeated startup wiring tests in:
   - `tests/test_api.py`
   - `tests/test_cli.py`
   - `tests/test_batch_cli.py`
   - `tests/test_eval_cli.py`
   - `tests/test_tasks.py`
3. Ensure assertions remain explicit at callsites.

### Slice 4: Documentation completion

Status: `Pending`

1. Create `docs/testing-patterns.md`.
2. Add fixture catalog + usage examples.
3. Cross-link from:
   - `docs/testing_plan.md`
   - `AGENTS.md` (if appropriate in later doc pass)
   - README docs index section (if maintained).

## Validation Matrix

- For each slice:
  - `task lint`
  - targeted pytest modules touched by the slice
  - `task test` before merge
- For doc-only slice:
  - markdown readability check in review
  - verify examples match current fixture names and signatures

## Risks and Mitigations

- Risk: over-centralizing fixtures makes tests harder to understand.
  - Mitigation: keep fixtures local unless reused across modules.
- Risk: hidden fixture side effects.
  - Mitigation: avoid autouse except for truly global concerns.
- Risk: fixture churn causing merge conflicts.
  - Mitigation: small slices and low overlap PRs.

## Deliverables

- `docs/testing_plan.md` (this plan)
- `docs/testing-patterns.md` (detailed fixture/pattern reference)
- Incremental fixture consolidation PR(s)

## Acceptance Criteria

- Shared fixtures are discoverable in `tests/conftest.py`.
- Obvious duplicated setup in CLI/API/task tests is reduced.
- `docs/testing-patterns.md` is concise, actionable, and aligned with current repo practice.
- Test/lint pipelines stay green with no behavior regressions.

## Immediate Next Step

Execute Slice 2 (store fixture standardization) in a small PR and keep module-local wrapper fixtures where they improve readability.
