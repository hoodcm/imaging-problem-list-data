# Stream A: Restructure Orchestrator Core

Last updated: 2026-02-14
Status: Implemented (structure-first slice)
Owner/worktree: `/Users/talkasab/repos/imaging-problem-list` (`feature/restructure-orchestrator-core`)

## Goal

Introduce explicit orchestration stage boundaries and canonical progress/status messaging without changing extraction semantics yet.

## In scope

1. Create orchestrator module scaffold with deterministic stage function boundaries.
2. Route current worker extraction flow through orchestrator entrypoint.
3. Normalize worker status messages to canonical stage vocabulary.
4. Add targeted tests for stage sequence and failure-stage visibility.

## Out of scope

1. Full section-parallel extraction behavior changes.
2. New provider settings logic.
3. Coding bridge internals.
4. UI rendering changes.

## Canonical stage vocabulary

1. `preflight`
2. `sectionize`
3. `extract_sections`
4. `merge_dedupe`
5. `repair_failed_sections`
6. `validate_output`
7. `apply_coding`
8. `persist`
9. `completed`
10. `failed`

## Implementation plan

1. Add `src/finding_extractor/extraction_orchestrator.py`:
   1. define stage context model
   2. define stage execution helpers
   3. define orchestration entrypoint consumed by tasks
2. Update `src/finding_extractor/tasks.py` to emit canonical stage messages in deterministic order.
3. Keep existing extraction call path and validation behavior unchanged (structure-first refactor).
4. Ensure status callbacks remain backward compatible.

## Files expected to change

1. `src/finding_extractor/extraction_orchestrator.py` (new)
2. `src/finding_extractor/tasks.py`
3. `tests/test_tasks.py`
4. `docs/agent_restructuring.md` (status update only)

## Test plan

1. `uv run pytest tests/test_tasks.py -q`
2. Add tests for:
   1. canonical stage emission order in success path
   2. stage emission for failure path
   3. status callback compatibility

## Acceptance criteria

1. Worker status messages use canonical stage labels.
2. Existing extraction outputs remain unchanged.
3. Stream test scope is green.

## Progress

### 2026-02-14: Orchestrator skeleton + canonical stage status wiring

Shipped:

1. Added `src/finding_extractor/extraction_orchestrator.py` with:
   1. `run_orchestrated_extraction(...)` structure-first orchestration entrypoint.
   2. `format_stage_status(...)` for parseable stage status messages.
   3. explicit stage sequencing for:
      - `sectionize`
      - `extract_sections`
      - `merge_dedupe`
      - `repair_failed_sections`
      - `validate_output`
      - `apply_coding` (when enabled)
2. Updated `src/finding_extractor/tasks.py` to:
   1. route extraction flow through orchestrator entrypoint
   2. emit canonical preflight/persist/completed/failed stage messages
   3. preserve existing persistence and completion/failure semantics
3. Added tests in `tests/test_tasks.py` for:
   1. canonical stage emission order on success
   2. failed-stage status emission on exceptions

Validation:

1. `uv run pytest tests/test_tasks.py -q` -> 10 passed
2. `uv run ruff check src/finding_extractor/extraction_orchestrator.py src/finding_extractor/tasks.py tests/test_tasks.py` -> clean
