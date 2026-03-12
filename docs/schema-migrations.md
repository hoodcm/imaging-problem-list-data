# Schema Migrations Runbook

This is the operational guide for changing database schema in this repo.

Architecture/rationale lives in `docs/archive/migration-architecture.md` (historical). This document is the
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

Docker startup path (recommended):
```bash
task stack:up
```

`task stack:up` runs `task db:migrate:auto:stack` before starting API/worker.

Docker migration task equivalents:
```bash
task db:migrate:stack
task db:migrate:auto:stack
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
| `3d867b54ee78` | Baseline schema (consolidated) | All tables: `reports`, `extractions`, `corrections`, `jobs`, `users`. All columns including `study_description_hint`, `study_description`, `coded_finding_count`, `unresolved_finding_count`, `diagnostics_json`, `trace_id`, usage columns. |

Previous migration history was collapsed into a single baseline during the package restructuring. Existing SQLite databases should be dropped and recreated.

## Runtime Schema Preflight

When `--store` is enabled, `finding-extractor`, `finding-extractor-batch`, and API startup all call
`check_migration_current()` **before** `init()` (which runs `create_all`). This ensures a fresh or
outdated DB never gets app tables created without a proper Alembic migration. If the DB revision
doesn't match the expected head (`ExtractionStore.EXPECTED_REVISION`), startup fails fast with an
actionable error directing the operator to run `task db:migrate`.

This means `uv run finding-extractor-api` now has the same schema preflight discipline as the CLI
store paths: it consumes a migrated DB, but does not bootstrap one.

When adding a new migration, update `EXPECTED_REVISION` in `src/finding_extractor/db/engine.py` to match the new head revision. `ExtractionStore.EXPECTED_REVISION` remains a public alias for callers.

## Safety Notes

- Do not edit production-like DB schema manually outside Alembic revisions.
- For destructive or high-risk changes, back up DB files first.
- SQLite has limited `ALTER TABLE`; prefer additive multi-step migrations where practical.

## Related Docs

- Migration architecture (historical): `docs/archive/migration-architecture.md`
- Persistence internals: `docs/persistence-internals.md`
- DevOps commands: `docs/dev-ops.md`
