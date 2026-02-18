# Testing Plan

**Status:** Active follow-up plan (post-Stage 3 logging work)  
**Execution State (February 12, 2026):**
- `Slice 1` completed.
- `Slice 2` completed.
- `Slice 3` completed.
- `Slice 4` completed (guidance split + documentation rollout).

## Purpose

Improve test maintainability and contributor onboarding by:
- reducing fixture duplication in test code, and
- clearly separating general pytest best-practice guidance from this repo's project-specific testing conventions.

## Goals

- Keep shared fixtures consolidated in `tests/conftest.py` where reuse is real.
- Avoid brittle ad hoc import patterns across pytest modules.
- Publish project-specific testing practices in `docs/`.
- Package reusable pytest guidance as a local agent skill for future tasks.

## Non-Goals

- No broad behavior-changing test rewrites.
- No migration away from pytest.
- No new testing architecture beyond lightweight documentation/skill packaging.

## Guiding Rules

- Prefer pytest-native fixture sharing via `tests/conftest.py`.
- Keep local fixtures local when extraction to shared scope hurts readability.
- Keep guidance split clean:
  - reusable/general testing practices in `.agents/skills/`
  - repo-specific testing practices in `docs/`
- Keep slices small and reviewable with green checks.

## Current Snapshot

- Shared fixtures now exist for:
  - settings cache reset (`tests/conftest.py`)
  - structured log context capture (`tests/conftest.py`)
  - shared CLI runner (`tests/conftest.py`)
  - shared async store factory (`tests/conftest.py`)
  - shared runtime logging spy (`tests/conftest.py`)
- Documentation split now in place:
  - reusable pytest skill: `.agents/skills/pytest-testing-patterns/`
  - project-specific conventions: `docs/testing-practices.md`

## Prioritized Workstreams

### Workstream A: Shared Fixtures (completed)

1. `DONE` — `cli_runner` fixture and migrations in CLI test modules.
2. `DONE` — `store_factory` fixture and migrations in store/API/task modules.
3. `DONE` — `runtime_logging_spy` fixture and startup wiring migration.
4. `DONE` — keep behavior assertions unchanged across migration slices.

### Workstream B: Guidance Split (Slice 4)

1. `DONE` — Create reusable pytest skill in `.agents/skills/pytest-testing-patterns/`:
   - `SKILL.md` with workflow and decision rules
   - focused `references/` docs for general best practices
2. `DONE` — Create `docs/testing-practices.md` for this repo only:
   - fixture catalog from `tests/conftest.py`
   - test-type patterns used in this codebase
   - anti-patterns and update policy
3. `DONE` — Cross-link docs for discoverability:
   - `docs/testing_plan.md`
   - `AGENTS.md`
   - `CLAUDE.md`
   - `README.md` docs index

### Workstream C: Incremental Adoption

1. Apply guidance during normal feature work (no mass rewrites).
2. Keep changes scoped and reversible.
3. Validate with `task lint` and `task test` whenever behavior-affecting test edits occur.

## Execution Slices (PR-friendly)

### Slice 1: CLI runner standardization

Status: `Completed`

### Slice 2: Store fixture standardization

Status: `Completed`

### Slice 3: Runtime logging patch helper

Status: `Completed`

### Slice 4: Guidance split + docs rollout

Status: `Completed`

1. Rework plan to reflect two-track documentation strategy.
2. Add `.agents/skills/pytest-testing-patterns/`.
3. Add `docs/testing-practices.md` and fixture catalog.
4. Update cross-links in key onboarding docs.

## Validation Matrix

- Fixture/code slices:
  - `task lint`
  - targeted pytest modules
  - `task test`
- Documentation/skill slices:
  - markdown readability + link sanity review
  - fixture names/signatures match `tests/conftest.py`

## Risks and Mitigations

- Risk: duplicated guidance across skill and docs.
  - Mitigation: keep generic vs project-specific boundaries explicit.
- Risk: over-centralized fixtures reducing readability.
  - Mitigation: only promote fixtures with clear multi-module reuse.
- Risk: documentation drift.
  - Mitigation: require fixture catalog updates when shared fixtures change.

## Deliverables

- `docs/testing_plan.md` (this plan)
- `.agents/skills/pytest-testing-patterns/` (reusable pytest guidance)
- `docs/testing-practices.md` (project-specific testing conventions)
- Incremental fixture consolidation already delivered in slices 1-3

## Acceptance Criteria

- Shared fixtures are discoverable in `tests/conftest.py`.
- Duplicated setup is reduced in high-value test modules (slices 1-3 done).
- Reusable pytest guidance is available as a skill.
- Project-specific testing guidance is concise and maintained in `docs/testing-practices.md`.
- Documentation cross-links are updated in onboarding docs.

## Immediate Next Step

Use the new split guidance during normal feature work and keep fixture catalog/docs synchronized with future shared fixture changes.
