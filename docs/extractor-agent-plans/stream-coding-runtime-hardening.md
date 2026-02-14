# Stream C: Coding Runtime Hardening

Last updated: 2026-02-14
Status: Active
Owner/worktree: `/Users/talkasab/repos/imaging-problem-list-provider` (`feature/coding-bridge-runtime-hardening`)

## Goal

Improve coding bridge runtime efficiency and mapping quality without changing extraction success semantics.

## In scope

1. Reuse coding indexes across calls instead of opening per extraction.
2. Use `region` filtering for anatomic location search when location context is available.
3. Keep coding non-fatal for extraction jobs.
4. Add tests for lifecycle reuse and region behavior.

## Out of scope

1. API response schema changes.
2. UI rendering changes.
3. Agent-based coding implementation.

## Implementation plan

1. Update `src/finding_extractor/coding_bridge.py`:
   1. Add lazy, reusable index holder for `Index` and `AnatomicLocationIndex`.
   2. Add guarded initialization for concurrent calls.
   3. Add close/reset helper for tests and lifecycle cleanup hooks.
2. Improve location coding:
   1. Map `FindingLocation.body_region` to supported `region` values.
   2. Pass `region` to `AnatomicLocationIndex.search(...)` when mapped.
   3. Fall back to unfiltered search when mapping unavailable.
3. Maintain existing per-finding exception isolation behavior.

## Files expected to change

1. `src/finding_extractor/coding_bridge.py`
2. `tests/test_coding_bridge.py`
3. `tests/test_tasks.py` (if integration assertions need update)

## Test plan

1. `uv run pytest tests/test_coding_bridge.py tests/test_tasks.py -q`

## Acceptance criteria

1. Repeated `apply_coding()` calls do not reopen indexes every invocation.
2. Region-aware search is used when available.
3. Coding failure remains non-fatal to extraction completion.
4. Stream test scope is green.
