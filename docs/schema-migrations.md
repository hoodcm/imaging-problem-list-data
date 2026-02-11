# Schema Migrations Runbook

This is the operational guide for changing database schema in this repo.

Architecture/rationale lives in `docs/migration-architecture.md`. This document is the
day-to-day "how".

## First-Time Setup by DB State

Use exactly one of these paths:

1. New/empty local DB:
```bash
task db:migrate
```

2. Existing DB created before Alembic adoption (tables already exist):
```bash
task db:stamp:baseline
task db:migrate
```

Docker equivalents:
```bash
task db:migrate:stack
task db:stamp:baseline:stack
```

## Standard Schema Change Workflow

1. Update SQLModel schema in code.
2. Generate a migration:
```bash
task db:revision MSG="describe schema change"
```
3. Review/edit generated revision in `alembic/versions/`.
4. Apply migrations locally:
```bash
task db:migrate
```
5. Validate no drift and run tests:
```bash
task db:check
task test:unit
```
6. Commit schema code + migration file in the same PR.

## Required PR Checklist

- Exactly one Alembic head:
```bash
task db:heads
```
- Current revision resolves cleanly:
```bash
task db:current
```
- Drift check passes:
```bash
task db:check
```
- Unit tests pass:
```bash
task test:unit
```

## Migration History

| Revision | Description | Notes |
|----------|-------------|-------|
| `17f8ebc6c608` | Baseline schema | `reports`, `extractions`, `corrections`, `jobs` tables |
| `7537480089ba` | Add usage columns | 7 nullable columns on `extractions`: `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `model_requests`, `duration_ms`, `usage_details_json` |
| `a3f1c8b2d4e6` | Add job status message | Nullable `status_message` column on `jobs` for in-flight progress visibility |

All new columns added to existing tables should be nullable to avoid backfill complexity. SQLite `batch_alter_table` is used for safe column addition.

## Runtime Schema Preflight

When `--store` is enabled, both `finding-extractor` and `finding-extractor-batch` check the `alembic_version` table before processing. If the DB revision doesn't match the expected head (`ExtractionStore.EXPECTED_REVISION`), the CLI fails fast with an actionable error directing the user to run `task db:migrate`.

When adding a new migration, update `EXPECTED_REVISION` in `src/finding_extractor/store.py` to match the new head revision.

## Safety Notes

- Do not edit production-like DB schema manually outside Alembic revisions.
- For destructive or high-risk changes, back up DB files first.
- SQLite has limited `ALTER TABLE`; prefer additive multi-step migrations where practical.

## Related Docs

- Migration architecture: `docs/migration-architecture.md`
- Persistence internals: `docs/persistence-internals.md`
- DevOps commands: `docs/dev-ops.md`
