# CLI Persistence Notes And Next Steps

This document captures what is implemented today and what remains as follow-up work.

Status:
- Implemented: optional CLI persistence (`--store`, `--db-path`).
- Implemented: `_storage` metadata in JSON output and persistence block in table output.
- Implemented: single async orchestration boundary via `asyncer.runnify(...)`.
- Remaining: incremental UX features and additional CLI tests listed below.

## Goals

- Keep existing CLI extraction behavior unchanged when persistence is not requested.
- Add optional persistence writes for experiment tracking.
- Preserve clear provenance in CLI output.
- Keep sync/async boundaries simple and explicit.

## Current CLI Flags

- `--store/--no-store` (default: `--no-store`)
- `--db-path PATH` (default from env or `.finding_extractor.db`)
- Future: `--store-include-validation/--store-skip-validation` (currently validation is stored when computed)

Environment:
- `IPL_DB_PATH` fallback for DB path

## Current UX Behavior

1. Read report text.
2. Run extraction (existing behavior).
3. If `--store`:
   - upsert report
   - create extraction record
   - include storage metadata in JSON/table output
4. Exit codes remain:
   - `0` success
   - `1` extraction/persistence runtime error
   - `2` validation failure (when `--validate` is enabled)

## JSON Output Additions

When `--store` is enabled, include:

```json
{
  "_storage": {
    "db_path": ".finding_extractor.db",
    "report_id": "uuid",
    "report_seen_before": false,
    "extraction_id": "uuid",
    "model_name": "openai:gpt-5-mini",
    "reasoning_effort": "medium",
    "extracted_at": "2026-02-08T12:00:00+00:00"
  }
}
```

## Table Output Additions

Append section:

```text
PERSISTENCE:
  DB Path: .finding_extractor.db
  Report ID: <uuid>
  Extraction ID: <uuid>
  Model: openai:gpt-5-mini
  Timestamp: 2026-02-08T12:00:00+00:00
```

## Command Examples

No persistence (default):

```bash
uv run finding-extractor sample_data/example2/xr_chest_20210614.md --exam-type "Chest XR"
```

With persistence:

```bash
uv run finding-extractor sample_data/example2/xr_chest_20210614.md \
  --exam-type "Chest XR" \
  --store \
  --db-path .finding_extractor.db
```

With persistence + validation:

```bash
uv run finding-extractor sample_data/example2/xr_chest_20210614.md \
  --exam-type "Chest XR" \
  --store \
  --validate
```

## Integration Pattern

The CLI is synchronous. The store is async.

Recommended pattern:
- Create one async orchestration function for all persistence calls in a single run.
- Bridge once at CLI boundary with `asyncer.runnify(...)`.
- Avoid creating multiple per-method wrappers that create separate event loops.

Pseudo-shape:

```python
async def persist_run(...):
    store = ExtractionStore(db_path)
    try:
        report = await store.upsert_report(...)
        extraction = await store.create_extraction(...)
        return metadata
    finally:
        await store.close()
```

## Remaining Work

1. Add a focused CLI test for persistence-failure error messaging/exit code (`1`).
2. Add a focused CLI test for validation failure exit code (`2`) with `--store` enabled.
3. Decide whether to add `--store-include-validation/--store-skip-validation` for explicit control of validation payload storage.
