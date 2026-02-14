# Stream D: Coding API/UI Contract

Last updated: 2026-02-14
Status: Active
Owner/worktree: `/Users/talkasab/repos/imaging-problem-list-ui` (`feature/coding-progress-ui-api-contract`)

## Goal

Expose persisted coding data in API/store models and render coding/progress information in the extractor UI.

## In scope

1. Include coding payload in extraction detail responses.
2. Include coding summary counts in extraction summaries.
3. Render coding status in extractor UI (coded/unresolved and null-safe fallback).
4. Align progress display with canonical stage vocabulary.

## Out of scope

1. Coding bridge internals.
2. Provider fail-fast logic.
3. Full orchestrator behavior changes.

## Implementation plan

1. Update `src/finding_extractor/store.py`:
   1. deserialize `coding_json` into typed `CodingBridgeResult`
   2. thread coding data through stored extraction detail/list mapping
2. Update `src/finding_extractor/api_models.py`:
   1. add `coding_result: CodingBridgeResult | None` to extraction detail response
   2. add `coding_coded_count` and `coding_unresolved_count` to extraction summary response
3. Update `extractor-ui/app.js`:
   1. render coding summary and per-finding coding badges
   2. render unresolved list
   3. render “coding unavailable” when `coding_result` is null
   4. map stage labels from worker status to user-visible progress

## Files expected to change

1. `src/finding_extractor/store.py`
2. `src/finding_extractor/api_models.py`
3. `src/finding_extractor/api_routes.py` (only if mapping glue changes)
4. `extractor-ui/app.js`
5. `tests/test_store.py`
6. `tests/test_api.py`
7. `tests/test_ui.py`

## Test plan

1. `uv run pytest tests/test_store.py tests/test_api.py tests/test_ui.py -q`

## Acceptance criteria

1. Extraction detail API includes coding payload when persisted.
2. Extraction summary API includes coding counts.
3. UI correctly shows coded/unresolved states and null-safe fallback.
4. Stream test scope is green.
