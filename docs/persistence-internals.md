# Persistence Internals

This guide is for maintainers modifying schema or persistence behavior.

Primary implementation:
- `src/finding_extractor/db/store.py` — public `ExtractionStore` facade
- `src/finding_extractor/db/engine.py` — engine/session lifecycle and migration preflight
- `src/finding_extractor/db/reports.py`
- `src/finding_extractor/db/extractions.py`
- `src/finding_extractor/db/jobs.py`
- `src/finding_extractor/db/corrections.py`
- `src/finding_extractor/db/users.py`

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
- `patient_id` (nullable — optional patient identifier)
- `created_at`

### `extractions`

- `id` (PK)
- `report_id` (FK -> `reports.id`, indexed)
- `created_at` (indexed)
- `model_name`
- `reasoning_effort` (nullable)
- `study_description_hint` (nullable)
- `study_description` (nullable denormalized)
- `study_date` (nullable denormalized)
- `modality` (nullable denormalized)
- `body_region` (nullable denormalized)
- `body_part` (nullable denormalized)
- `contrast` (nullable denormalized)
- `laterality` (nullable denormalized)
- `finding_count` (Integer, default 0 — `len(extraction.findings)` at persist time)
- `coded_finding_count` (nullable Integer — inline coding "coded" count at persist time)
- `unresolved_finding_count` (nullable Integer — inline coding "unmapped" count at persist time)
- `diagnostics_json` (nullable — serialized `PipelineDiagnostics`)
- `trace_id` (nullable — OpenTelemetry trace ID hex string for Logfire linkage)
- `extraction_json`
- `validation_json` (nullable)
- `input_tokens` (nullable, Integer)
- `output_tokens` (nullable, Integer)
- `cache_read_tokens` (nullable, Integer)
- `cache_write_tokens` (nullable, Integer)
- `model_requests` (nullable, Integer — number of API requests including retries)
- `duration_ms` (nullable, Integer — wall-clock extraction time)
- `usage_details_json` (nullable — provider-specific extras as JSON blob)

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
- `created_by` (nullable — legacy free-text author field)
- `username` (nullable FK -> `users.username` — formal user attribution)
- `created_at`

Note: `created_by` is preserved for backward compatibility with existing corrections. New corrections should use `username` to reference a formal user account.

### `users`

- `username` (PK, string)
- `name` (string — display name)
- `email` (string — contact email)
- `created_at`

Purpose:
- Formal user accounts for correction attribution
- Seeded with default user `talkasab` via migration

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

`ExtractionStore` remains the caller-facing API. Its implementation now delegates into the domain modules above rather than housing all persistence logic in one file.

Core methods:
- `init()` / `close()`
- `upsert_report(report_text, source_ref=None, patient_id=None)`
- `create_extraction(...)`
- `record_correction(..., username=None, created_by=None)`
- `list_corrections(...)`

Read methods added for API layer:
- `get_report(...)`
- `list_reports(...)`
- `get_extraction(...)`
- `list_extractions(...)`

User management methods:
- `create_user(username, name, email)` — upsert semantics
- `get_user(username)` — returns `StoredUser` or `None`
- `list_users()` — alphabetically ordered

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

### Denormalized Exam Info and Metadata Strategy

All `ExamInfo` fields are denormalized to dedicated columns on `extractions` to enable summary views and SQL-level filtering without JSON deserialization. `finding_count` is computed at persist time. `diagnostics_json` captures the full `PipelineDiagnostics` dataclass (chunk counts, repair stats, validator stats) for the detail view. `trace_id` stores the OpenTelemetry trace ID at persist time, linking the extraction to its Logfire trace for prompt reproducibility.

### Usage Data Strategy

Token usage is stored in dedicated nullable columns (`input_tokens`, `output_tokens`, etc.) rather than inside `extraction_json`. This allows direct SQL queries for cost/latency analytics without JSON parsing. Provider-specific extra fields go into `usage_details_json` as a catch-all.

All usage columns are nullable because:
- older extractions pre-date usage capture
- some providers (e.g., Ollama) may not report usage
- usage capture is best-effort (failures are logged but don't block extraction)

## Correction Validation Rules

- `add_finding` requires `proposed_finding`
- `update_finding` requires `target_finding_index` or `target_json_path`
- `update_finding` with `target_finding_index` must resolve to an existing finding path in extraction payload
- `comment` requires non-empty `comment`
- `username` (if provided) must reference an existing user in the `users` table (enforced by FK constraint)

## Testing Strategy

- `tests/test_store.py` covers table behavior and conversion.
- `tests/test_api.py` covers endpoint behavior with in-memory broker.
- `tests/test_tasks.py` covers task error sanitization behavior.

Known gap:
- No real worker-process integration test yet (tracked in `docs/archive/api-server.md`).

## Migration Policy (Current)

- Alembic is the schema migration mechanism for evolving existing DB files.
- Baseline revision is `17f8ebc6c608` in `alembic/versions/17f8ebc6c608_baseline_schema.py`.
- Usage columns added in `7537480089ba` in `alembic/versions/7537480089ba_add_usage_columns.py`.
- Job status message column added in `a3f1c8b2d4e6` in `alembic/versions/a3f1c8b2d4e6_add_job_status_message.py`.
- **Users, patient_id, and correction author added in `17d9bf28412d` in `alembic/versions/17d9bf28412d_add_users_patient_id_correction_author.py`.**
  - Added `users` table with seeded default user `talkasab`
  - Added `patient_id` to `reports` (nullable)
  - Added `username` FK to `corrections` (nullable, references `users.username`)
- **All migrations collapsed into single baseline `3d867b54ee78` during package restructuring.**
  - Columns `laterality`, `finding_count`, `coded_finding_count`, `unresolved_finding_count`, `diagnostics_json`, `trace_id` included in baseline schema.
- For schema changes intended for existing/shared DBs:
  1. update SQLModel metadata
  2. generate migration (`task db:revision MSG="..."`)
  3. review migration script
  4. apply and verify (`task db:migrate`, `task db:check`)
- For existing DBs created before Alembic adoption:
  - run `task db:stamp:baseline` once, then proceed with normal migrate flow
- `SQLModel.metadata.create_all` is used for ephemeral test DBs and explicit `init()` flows.
- CLI store paths (`finding-extractor --store`, `finding-extractor-batch --store`) run `check_migration_current()` **before** `init()`, so `create_all` is not invoked on unmigrated DBs in those paths.
- API startup currently calls `init()` directly and therefore assumes the DB has already been migrated as part of deployment/ops workflow (`task db:migrate`).

## Related Docs

- Usage: `docs/persistence-usage.md`
- API internals: `docs/api-internals.md`
- Migration architecture (historical): `docs/archive/migration-architecture.md`
- Schema migration runbook: `docs/schema-migrations.md`
