# Persistence Internals

This guide is for maintainers modifying schema/store behavior.

Primary implementation:
- `src/finding_extractor/store.py`

## Technology

- ORM layer: SQLModel (on SQLAlchemy)
- DB: SQLite
- Async driver: `aiosqlite`
- Engine: `create_async_engine("sqlite+aiosqlite:///...")`
- Session pattern: `async_sessionmaker(..., class_=AsyncSession)`

## Connection Pragmas (Applied on Connect)

Every SQLite connection applies:
- `PRAGMA journal_mode=WAL`
- `PRAGMA busy_timeout=5000`
- `PRAGMA synchronous=NORMAL`
- `PRAGMA foreign_keys=ON`

Rationale: safe API + worker concurrency on one host with short write transactions.

## Active Schema

### `reports`

- `id` (PK, UUID string)
- `text_hash` (unique/indexed SHA-256)
- `report_text`
- `source_ref` (nullable)
- `created_at`

### `extractions`

- `id` (PK)
- `report_id` (FK -> `reports.id`, indexed)
- `created_at` (indexed)
- `model_name`
- `reasoning_effort` (nullable)
- `exam_description_hint` (nullable)
- `study_description` (nullable denormalized)
- `study_date` (nullable denormalized)
- `modality` (nullable denormalized)
- `body_part` (nullable denormalized)
- `extraction_json`
- `validation_json` (nullable)

### `corrections`

- `id` (PK)
- `extraction_id` (FK -> `extractions.id`, indexed)
- `target_finding_index` (nullable)
- `target_json_path` (nullable)
- `correction_type` (`add_finding|update_finding|comment`)
- `status` (`pending|accepted|rejected|applied`)
- `proposed_finding_json` (nullable)
- `attribute_overrides_json` (nullable)
- `comment` (nullable)
- `created_by` (nullable)
- `created_at`

### `jobs`

- `id` (PK, API-generated job UUID)
- `report_id` (FK -> `reports.id`, indexed)
- `status` (`pending|running|completed|failed`, indexed)
- `created_at` (indexed)
- `started_at` (nullable)
- `completed_at` (nullable)
- `extraction_id` (nullable FK -> `extractions.id`)
- `error` (nullable public error string)

Purpose:
- Distinguish unknown jobs (`404`) from queued/running jobs.
- Persist async state transitions independently of queue internals.

## Store API Contract

Core methods:
- `init()` / `close()`
- `upsert_report(...)`
- `create_extraction(...)`
- `record_correction(...)`
- `list_corrections(...)`

Read methods added for API layer:
- `get_report(...)`
- `list_reports(...)`
- `get_extraction(...)`
- `list_extractions(...)`

Job lifecycle methods:
- `create_job(...)`
- `get_job(...)`
- `mark_job_running(...)`
- `mark_job_completed(...)`
- `mark_job_failed(...)`

## JSON Payload Strategy

Nested extraction content remains serialized in `extractions.extraction_json`.

Benefits:
- low schema churn while extraction schema evolves
- straightforward persistence for nested Pydantic models

Tradeoff:
- analytics queries over deep fields rely on SQLite JSON functions.

## Correction Validation Rules

- `add_finding` requires `proposed_finding`
- `update_finding` requires `target_finding_index` or `target_json_path`
- `update_finding` with `target_finding_index` must resolve to an existing finding path in extraction payload
- `comment` requires non-empty `comment`

## Testing Strategy

- `tests/test_store.py` covers table behavior and conversion.
- `tests/test_api.py` covers endpoint behavior with in-memory broker.
- `tests/test_tasks.py` covers task error sanitization behavior.

Known gap:
- No real worker-process integration test yet (tracked in `docs/api-server.md`).

## Migration Policy (Current)

- Alembic is the schema migration mechanism for evolving existing DB files.
- Baseline revision is `17f8ebc6c608` in `alembic/versions/17f8ebc6c608_baseline_schema.py`.
- For schema changes intended for existing/shared DBs:
  1. update SQLModel metadata
  2. generate migration (`task db:revision MSG="..."`)
  3. review migration script
  4. apply and verify (`task db:migrate`, `task db:check`)
- For existing DBs created before Alembic adoption:
  - run `task db:stamp:baseline` once, then proceed with normal migrate flow
- `SQLModel.metadata.create_all` remains acceptable for ephemeral DB bootstrap (tests/new local files), but it is not a substitute for Alembic revisions on existing DBs.

## Related Docs

- Usage: `docs/persistence-usage.md`
- API internals: `docs/api-internals.md`
- Migration architecture: `docs/migration-architecture.md`
