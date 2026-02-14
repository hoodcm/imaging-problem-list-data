# Stream D: Coding API/UI Contract

Last updated: 2026-02-14
Status: Complete
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
   3. render "coding unavailable" when `coding_result` is null
   4. map stage labels from worker status to user-visible progress

## Files changed

1. `src/finding_extractor/store.py` - Added `coding_coded_count`/`coding_unresolved_count` to `StoredExtraction`, `coding_result` to `StoredExtractionDetail`, helper functions for deserialization
2. `src/finding_extractor/api_models.py` - Added coding fields to `ExtractionSummaryResponse` and `ExtractionDetailResponse`, updated mapping functions
3. `extractor-ui/app.js` - Added stage label mapping, coding helper methods, updated mock data with coding payload
4. `extractor-ui/index.html` - Added coding section, per-finding coding/location badges, unresolved findings list, progress stage label in extracting view
5. `tests/test_store.py` - Added `test_create_extraction_with_coding_persists_and_round_trips`, `test_extraction_without_coding_returns_null`
6. `tests/test_api.py` - Added `test_extraction_detail_includes_coding_result`, `test_extraction_detail_null_coding_when_absent`, `test_extraction_summary_includes_coding_counts`
7. `tests/test_ui.py` - Added `test_coding_section_present`, `test_coding_badge_on_finding`, `test_location_coding_on_finding`

## Test plan

1. `uv run pytest tests/test_store.py tests/test_api.py tests/test_ui.py -q` - All 118 tests pass

## Acceptance criteria

1. Extraction detail API includes coding payload when persisted. **Done**
2. Extraction summary API includes coding counts. **Done**
3. UI correctly shows coded/unresolved states and null-safe fallback. **Done**
4. Stream test scope is green. **Done** (118/118 pass)

## Conflicts with other streams

None detected. Changes are confined to:
- Store layer: only added new fields to dataclasses and new helper functions (no changes to existing logic)
- API models: only added new optional fields and threading (backward compatible)
- UI: additive changes to rendering (no existing DOM structure modified)
- Files `api_routes.py` was not modified (mapping glue unchanged)
