# Persistence Internals

This guide is for developers/agents extending or changing the persistence layer.

Primary implementation:
- `src/finding_extractor/store.py`

## Technology

- ORM: SQLModel (on top of SQLAlchemy)
- Database: SQLite
- Async driver: `aiosqlite`
- Engine creation: `create_async_engine(f"sqlite+aiosqlite:///{db_path}")`
- Session pattern: `async_sessionmaker(..., class_=AsyncSession)`
- Test pattern: native `pytest-asyncio` async tests/fixtures (no sync wrappers in tests)

## Active Schema

### `reports`

Purpose:
- Deduplicated source report store.

Columns:
- `id` (PK, UUID string)
- `text_hash` (unique/indexed SHA-256 of report text)
- `report_text`
- `source_ref` (nullable)
- `created_at` (UTC ISO timestamp)

### `extractions`

Purpose:
- One row per extraction run, including model metadata and payload snapshot.

Columns:
- `id` (PK, UUID string)
- `report_id` (FK to `reports.id`, indexed)
- `created_at` (indexed)
- `model_name`
- `reasoning_effort` (nullable)
- `exam_description_hint` (nullable)
- `study_description` (nullable denormalized convenience field)
- `study_date` (nullable denormalized convenience field)
- `modality` (nullable denormalized convenience field)
- `body_part` (nullable denormalized convenience field)
- `extraction_json` (serialized `ReportExtraction`)
- `validation_json` (nullable serialized validation payload)

### `corrections`

Purpose:
- Human feedback and revision workflow primitives.

Columns:
- `id` (PK, UUID string)
- `extraction_id` (FK to `extractions.id`, indexed)
- `target_finding_index` (nullable)
- `target_json_path` (nullable, e.g. `$.findings[0]`)
- `correction_type` (`add_finding`, `update_finding`, `comment`)
- `status` (`pending`, `accepted`, `rejected`, `applied`)
- `proposed_finding_json` (nullable)
- `attribute_overrides_json` (nullable)
- `comment` (nullable)
- `created_by` (nullable)
- `created_at`

Constraints:
- Check constraint for `correction_type`
- Check constraint for `status`

## JSON Payload Strategy

Nested extraction content (findings, finding attributes, non-finding segments) is stored in:
- `extractions.extraction_json`

Rationale:
- Simpler schema and lower migration burden while extraction shape evolves.
- Top-level entities remain relational and queryable.

Tradeoff:
- Deep analytics queries require SQLite JSON functions and may need indexing strategy later.

## Querying JSON Child Content

Example: expand findings

```sql
SELECT
  e.id AS extraction_id,
  json_extract(f.value, '$.finding_name') AS finding_name,
  json_extract(f.value, '$.presence') AS presence
FROM extractions e,
json_each(e.extraction_json, '$.findings') AS f;
```

Example: filter by finding name

```sql
SELECT
  e.id AS extraction_id,
  json_extract(f.value, '$.report_text') AS report_text
FROM extractions e,
json_each(e.extraction_json, '$.findings') AS f
WHERE lower(json_extract(f.value, '$.finding_name')) = 'pneumonia';
```

## Store API Contract

`ExtractionStore` methods:
- `await init()`
- `await upsert_report(report_text, source_ref=None) -> StoredReport`
- `await create_extraction(report_id, extraction, model_name, ...) -> StoredExtraction`
- `await get_finding_path(extraction_id, finding_index) -> str | None`
- `await record_correction(extraction_id, correction_type, ...) -> StoredCorrection`
- `await list_corrections(extraction_id) -> list[StoredCorrection]`
- `await close()`

Correction validation behavior:
- `add_finding` requires `proposed_finding`
- `update_finding` requires `target_finding_index` or `target_json_path`
- `comment` requires non-empty comment text

## Data Flow

1. Caller obtains report text.
2. Caller gets/creates `ReportExtraction` from the extraction pipeline.
3. If persistence is enabled, caller invokes store `upsert_report(...)`.
4. Caller invokes store `create_extraction(...)`.
5. Optional user correction rows are written via `record_correction(...)`.

## Testing Strategy

- `tests/test_store.py` owns persistence/schema behavior:
  - row-level assertions
  - JSON payload storage checks
  - correction constraints and targeting behavior
- `tests/test_cli.py` owns CLI contract behavior:
  - flag behavior (`--store/--no-store`, `--db-path`)
  - output contract (`_storage` in JSON, `PERSISTENCE` in table)
  - report dedupe metadata behavior (`report_seen_before`)

This keeps schema coupling localized to store tests and keeps CLI tests stable across internal schema refactors.

## Migration Notes

- New DB files get the active 3-table schema automatically.
- Old local DB files may still contain deprecated tables from earlier iterations.
- If schema changes are made, consider introducing explicit migration workflow.

## Related Docs

- Consumer guide: `docs/persistence-usage.md`
- CLI notes/future enhancements (archived): `docs/archive/persistence-cli-plan.md`
