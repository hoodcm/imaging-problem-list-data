# Plan: Decompose Persistence Internals and the Orchestrator

## Summary

Refactor `src/finding_extractor/db/store.py` and `src/finding_extractor/extractor/orchestrator/` into smaller internal modules, but do it with restraint:

- keep `ExtractionStore` as the public persistence boundary
- keep `finding_extractor.extractor.orchestrator` as the public orchestration boundary
- decompose internals aggressively where the files are doing too many things
- do not introduce new public repository abstractions unless the codebase actually needs them later

This is a structural cleanup, not a behavior change and not a backward-compatibility exercise. The goal is to improve readability, ownership, and future changeability without creating unnecessary API churn.

## Architecture decisions

### Persistence

Keep `ExtractionStore` as the top-level persistence API.

Rationale:

- it is already the package boundary exposed by `finding_extractor.db`
- it matches the current project complexity better than `ExtractionDatabase` plus five public repositories
- callers across API, worker, CLI, tests, and docs already treat it as the single persistence entrypoint
- the real problem is file size and mixed responsibilities inside `store.py`, not that the abstraction is wrong

What changes:

- `ExtractionStore` stays public
- `Stored*` return types stay public
- `store.py` becomes a thin facade/composition layer
- internal persistence logic moves into domain modules

What does not change:

- no schema changes
- no Alembic changes
- no new public `ExtractionDatabase`
- no public `ReportRepository` / `ExtractionRepository` / `JobRepository` / `CorrectionRepository` / `UserRepository`

### Orchestrator

Keep `finding_extractor.extractor.orchestrator` as the public orchestration facade because it is the correct package-level workflow boundary.

What changes:

- `orchestrator.py` stops being the place where all orchestration details live
- helper logic moves into focused internal modules
- existing `extractor/progress.py` remains the home for stage-status formatting helpers; do not create a duplicate progress module

What stays importable from `extractor.orchestrator`:

- `run_orchestrated_extraction`
- `OrchestrationResult`
- `ExtractionReviewDecision`
- `ExtractionReviewProblem`

`format_stage_status` should continue to come from `extractor.progress`, which already exists.

## Persistence decomposition

### Target module layout

- `db/__init__.py`
  - re-export `ExtractionStore` and public `Stored*` types
- `db/tables.py`
  - keep as the SQLModel row-definition module
- `db/engine.py`
  - engine creation
  - session factory
  - SQLite pragma wiring
  - `init()` support
  - `close()` support
  - migration-current check support
- `db/reports.py`
  - `StoredReport`, `StoredReportDetail`
  - report hashing helper
  - report row-to-domain conversion
  - report CRUD helpers
  - section-ingestion and backfill logic
- `db/extractions.py`
  - `StoredExtraction`, `StoredExtractionDetail`
  - extraction row-to-domain conversion
  - usage / diagnostics / coding-count serialization helpers
  - extraction CRUD helpers
  - finding-path lookup helper
- `db/jobs.py`
  - `StoredJob`
  - job row-to-domain conversion
  - job CRUD and transition helpers
- `db/corrections.py`
  - `StoredCorrection`
  - correction row-to-domain conversion
  - correction validation and persistence helpers
- `db/users.py`
  - `StoredUser`
  - user row-to-domain conversion
  - user CRUD helpers
- `db/store.py`
  - `ExtractionStore` only
  - thin facade delegating to internal modules

### Required shape

`ExtractionStore` should continue to own:

- configured DB path
- async engine lifetime
- session factory access
- `init()`
- `close()`
- `check_migration_current()`
- public method names already used by callers

The domain modules should own:

- `Stored*` dataclasses for that domain
- row-mapping helpers
- serialization/deserialization helpers
- domain-specific validation and CRUD implementation

### Implementation rules

- keep current public method names on `ExtractionStore`
- keep sessions internal to the persistence layer
- keep helper functions next to the domain that owns them
- do not introduce a catch-all `utils.py`
- prefer private module functions or private internal helper objects over new public repository classes
- keep report/extraction/correction coupling where it is real, for example `get_finding_path()` remaining with extraction persistence logic

### Persistence documentation updates

Update documentation as part of the persistence refactor, not at the end:

- update `CLAUDE.md` architecture notes so they describe `ExtractionStore` as a facade over the `db` package rather than a monolithic module
- update any docs that reference `db/store.py` as the place where all persistence logic lives
- update usage docs so import examples still use `ExtractionStore`, but internal-architecture docs describe the new module split
- update docs that describe migration checks and SQLite bootstrap so they point to `db/engine.py` and `db/tables.py`
- remove stale statements that imply `ExtractionStore` itself contains all CRUD implementation

## Orchestrator decomposition

### Target module layout

- `extractor/progress.py`
  - keep existing progress callback types and stage formatting helpers here
- `extractor/orchestrator/types.py`
  - public orchestration result types that need stable import re-exports
  - internal orchestration-only dataclasses only if moving them clearly helps readability
- `extractor/orchestrator/chunks.py`
  - section chunk construction
  - semantic chunk expansion
  - bounded-concurrency chunk execution helpers
  - chunk execution result structures if they are chunk-specific
- `extractor/orchestrator/merge.py`
  - finding source tagging
  - merge and dedupe helpers
  - usage aggregation
  - failed-chunk metadata collection
- `extractor/orchestrator/review.py`
  - review pass logic
  - feedback formatting for retry
  - optional re-extract flow
  - review-specific counters and bookkeeping
- `extractor/orchestrator/__init__.py`
  - thin public facade
  - re-exports of approved public types
  - re-exports `run_orchestrated_extraction(...)`
- `extractor/orchestrator/run.py`
  - workflow coordinator

### Required coordinator shape

`run_orchestrated_extraction(...)` should read as a top-level workflow, not an implementation dump:

1. build section chunks
2. expand chunks if semantic chunking is enabled
3. launch optional exam-info work
4. run first-pass chunk extraction
5. run repair attempts
6. merge successful chunk outputs
7. await/apply exam-info result
8. run review and optional re-extract
9. validate final extraction
10. build diagnostics
11. return `OrchestrationResult`

### Orchestrator implementation rules

- keep `extractor.orchestrator` as the import boundary
- do not duplicate logic already living in `extractor.progress`
- only move types into `orchestrator/types.py` when doing so improves clarity or preserves a stable public re-export
- keep chunking helpers, merge logic, and review logic out of the public facade
- reduce the orchestrator facade to a thin package-level entrypoint and keep `orchestrator/run.py` as a readable coordinator, roughly a few hundred lines at most

### Orchestrator documentation updates

Update documentation as part of the orchestrator refactor:

- update architecture docs so they describe `extractor.orchestrator` as a facade/coordinator, not a monolithic implementation file
- update any extraction-flow docs to reflect the internal split between chunk execution, merge logic, review logic, and orchestration types
- keep docs clear that `extractor.progress` remains the home for progress formatting helpers
- remove stale references that imply all orchestration behavior lives in one file

## Tests and verification

Keep these test files monolithic:

- `tests/test_store.py`
- `tests/test_extraction_orchestrator.py`

Rationale:

- they are convenient subsystem-level entrypoints
- the user wants them runnable as a whole without hunting across many files

Required test-organization cleanup inside those files:

- add or keep clear section headers, grouping comments, or test classes aligned to the new internal domains
- make it easy to see which part of persistence or orchestration each block is covering
- do not let the source split make the tests harder to navigate

Verification:

- `uv run pytest tests/test_store.py tests/test_extraction_orchestrator.py -q`
- `uv run pytest tests/test_api.py tests/test_tasks.py tests/test_cli.py tests/test_batch_cli.py -q`
- `task lint`
- `task test`

Acceptance criteria:

- `ExtractionStore` remains the public persistence API
- `store.py` is reduced to a thin facade/composition layer
- persistence implementation is split across clear domain modules
- `extractor.orchestrator` remains the public orchestration API
- `extractor/orchestrator/__init__.py` is a thin public facade and `extractor/orchestrator/run.py` is a readable coordinator rather than the full implementation
- `extractor.progress` remains the single home for stage-status formatting helpers
- no stale documentation remains describing the old monolithic layouts
- persistence and orchestration behavior remain unchanged

## Assumptions

- Breaking internal code layout is acceptable.
- Public persistence API churn is not desirable here because it does not buy enough.
- Public orchestrator facade stability is an architectural choice, not a compatibility concession.
- Tests remain single files by preference, but their internal organization should improve.
- This refactor does not change schema, migrations, external behavior, or runtime semantics.
