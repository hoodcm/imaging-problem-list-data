# Testing Plan

**Status:** Draft backlog (post-Stage 3 logging work)

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

## Current Snapshot

- Shared fixtures now exist for:
  - settings cache reset (`tests/conftest.py`)
  - structured log context capture (`tests/conftest.py`)
- Remaining opportunities from audit:
  - repeated `CliRunner()` construction across CLI test modules
  - repeated async `ExtractionStore` setup/teardown patterns
  - repeated runtime logging monkeypatch setup patterns

## Work Plan

### Phase 1: Fixture Consolidation (small, low-risk)

1. Add shared CLI runner fixture in `tests/conftest.py`.
2. Add shared async store factory fixture in `tests/conftest.py`:
   - keep simple local wrappers where per-module DB naming improves clarity.
3. Add helper fixture for runtime logging monkeypatch wiring:
   - support API/CLI/batch/eval/worker startup tests.
4. Refactor only high-duplication callsites first; avoid churn in stable modules.

### Phase 2: Pattern Documentation (required)

1. Create `docs/testing-patterns.md` as the canonical testing style guide.
2. Include a fixture catalog:
   - fixture name
   - scope
   - intended use
   - example usage
3. Document expected patterns:
   - when to use shared vs local fixtures
   - async fixture lifecycle patterns
   - monkeypatch patterns for runtime wiring
   - CLI testing patterns (`CliRunner`, isolated filesystem)
   - API testing patterns (`ASGITransport`, app lifespan)
   - logging/context assertion patterns
4. Include anti-patterns to avoid:
   - importing helper modules from `tests/` package paths
   - over-abstracting test data builders
   - fixture overuse for one-off setup

### Phase 3: Adoption + Validation

1. Apply patterns incrementally during normal feature work.
2. Keep change sets small and test-focused.
3. Validate with:
   - `task lint`
   - `task test`

## Deliverables

- `docs/testing_plan.md` (this plan)
- `docs/testing-patterns.md` (detailed fixture/pattern reference)
- Incremental fixture consolidation PR(s)

## Acceptance Criteria

- Shared fixtures are discoverable in `tests/conftest.py`.
- Obvious duplicated setup in CLI/API/task tests is reduced.
- `docs/testing-patterns.md` is concise, actionable, and aligned with current repo practice.
- Test/lint pipelines stay green with no behavior regressions.
