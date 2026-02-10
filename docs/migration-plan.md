# Migration Plan (Lightweight, Maintainable)

## Context

Current persistence bootstrap uses `SQLModel.metadata.create_all`, which is fine for creating a new local DB but not sufficient for safely evolving existing DB files over time.

This project is intentionally lightweight, so migration tooling should stay simple while still being reliable.

## Priority Relative to Other Plans

Execution priority for current planning docs:

1. **Migration foundation first** (this document)
2. **Config rationalization second** (`docs/config-plan.md`, env-first phases)
3. **Data-model consolidation third** (`docs/data-model-plan.md`, Track A first)

Reason: migration safety is a prerequisite for low-risk schema evolution; doing large
refactors before migration tooling increases rollback and data-integrity risk.

## Goals

- Keep schema evolution safe for existing data.
- Keep workflow minimal for a small team/repo.
- Avoid custom migration frameworks.
- Preserve fast local developer experience.

## Decision

Use Alembic as the single migration tool for schema changes.

Design principles:
- One migration stream (single head).
- Small, reviewable revisions.
- SQLite-compatible migration style (batch mode when needed).
- Manual review of autogenerate output before apply.

## Scope and Policy

- `create_all` remains acceptable for ephemeral/new test DB creation.
- Any schema change intended for existing/shared DBs must ship as an Alembic revision.
- No direct ad-hoc SQL schema edits outside migrations.

## Implementation Plan

1. Add dependency
- Add `alembic` to project dependencies (or dev dependencies if preferred by repo policy).

2. Initialize Alembic
- Create standard Alembic structure (`alembic.ini`, `alembic/`, `alembic/versions/`).

3. Wire metadata
- In Alembic `env.py`, set `target_metadata` to SQLModel metadata used by this app.

4. Configure SQLite-safe behavior
- Enable `render_as_batch=True` in migration context to support SQLite schema updates cleanly.

5. Add baseline migration
- Generate initial baseline revision representing current schema.
- For existing DBs already at this schema, use `alembic stamp <baseline_rev>` (no DDL execution).

6. Add task commands
- Add Taskfile wrappers:
  - `db:migrate` -> `alembic upgrade head`
  - `db:revision` -> `alembic revision --autogenerate -m "<msg>"`
  - `db:current` -> `alembic current`
  - `db:check` -> `alembic check`

7. CI guardrails
- Ensure single head (`alembic heads` should return one head).
- Run migration check (`alembic check`) to catch model drift.
- Run tests against a migrated DB path at least once in CI.

## Day-to-Day Developer Workflow

1. Change SQLModel schema.
2. Generate candidate migration:
   - `alembic revision --autogenerate -m "describe change"`
3. Review/edit migration script:
   - verify operations and naming
   - ensure downgrade path is reasonable
4. Apply locally:
   - `alembic upgrade head`
5. Run tests.
6. Commit schema change + migration in same PR.

## SQLite Notes

- SQLite has limited `ALTER TABLE`; some operations are implemented via table recreate/copy.
- Batch mode helps keep migration scripts predictable for SQLite.
- Prefer additive changes first where possible (new nullable columns, backfill, then tighten).

## Rollout Strategy

1. Introduce Alembic scaffolding and baseline revision without changing runtime behavior.
2. Stamp existing long-lived DBs to baseline.
3. Require Alembic revisions for all subsequent schema changes.
4. Optionally phase out reliance on `create_all` for non-ephemeral environments later.

## Risks and Mitigations

- Risk: autogenerate misses/overstates changes.
  - Mitigation: require manual review before merge.
- Risk: multiple heads from parallel work.
  - Mitigation: enforce single-head policy in CI.
- Risk: destructive migration on production-like DB.
  - Mitigation: backup + tested rollback notes before apply.

## Definition of Done

- Alembic initialized and committed.
- Baseline revision created and documented.
- Task commands added.
- CI checks for migration drift and single-head status added.
- Persistence docs updated to make Alembic the default schema evolution path.

## External References (Primary)

- SQLAlchemy guidance (use migration tool for schema upgrades):  
  https://docs.sqlalchemy.org/en/20/faq/metadata_schema.html#how-can-i-alter-table-objects-with-the-sqlalchemy-api
- Alembic autogenerate workflow and limits:  
  https://alembic.sqlalchemy.org/en/latest/autogenerate.html
- Alembic batch mode for SQLite migrations:  
  https://alembic.sqlalchemy.org/en/latest/batch.html
- SQLite ALTER TABLE limitations:  
  https://www.sqlite.org/lang_altertable.html
