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

## Safety Notes

- Do not edit production-like DB schema manually outside Alembic revisions.
- For destructive or high-risk changes, back up DB files first.
- SQLite has limited `ALTER TABLE`; prefer additive multi-step migrations where practical.

## Related Docs

- Migration architecture: `docs/migration-architecture.md`
- Persistence internals: `docs/persistence-internals.md`
- DevOps commands: `docs/dev-ops.md`
