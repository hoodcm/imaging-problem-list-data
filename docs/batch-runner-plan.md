# Batch Runner Plan (V1 Local Only)

Date: 2026-02-11
Last updated: 2026-02-14

## Status Update (2026-02-14)

V1 is now hardened with runtime fail-fast preflight behavior:

1. `finding-extractor-batch run` prints a conservative runtime preflight before execution.
2. Over-budget runs fail fast by default (`--max-predicted-runtime-seconds`, default `900`).
3. Intentionally long runs require explicit override (`--allow-slow`).
4. Preflight logic is shared with eval CLI via `src/finding_extractor/runtime_budget.py` (no duplicated guard math/message logic).

## Purpose

Provide a first-class batch extraction CLI that can process many report files with:

1. Interactive mode (live status in terminal)
2. Detached mode (background run + later status checks)

V1 is intentionally local/in-process only.

## Explicit Boundaries (Non-Goals for V1)

1. No new database tables
2. No direct TaskIQ integration from this CLI
3. No attempt to create a second queue system
4. No distributed workers / multi-host orchestration

Rationale: avoid re-implementing broker semantics and keep V1 aligned with current codebase simplicity.

## Design Principles

1. Reuse existing extraction code paths (`extract_findings`, `validate_extraction`, optional `ExtractionStore`)
2. Keep one execution engine shared by interactive and detached modes
3. Persist lightweight run state to local files for visibility and recoverability
4. Make future API/TaskIQ-backed mode additive, not a rewrite

## Runtime Modes

## Interactive

- Starts batch run and continuously prints:
  - overall counts (`done/ok/skipped/failed/timeout`)
  - per-worker active file
  - per-worker elapsed runtime
- Exits with non-zero code if any file fails or times out.

## Detached

- Starts same local runner in background
- Immediately returns `run_id`
- Writes run metadata for later inspection
- Status is observed via `status` command

## Architecture (V1)

## Core engine

- Async worker pool with bounded concurrency (`workers`)
- Per-file timeout (`timeout_seconds`)
- Per-file retries (`retries`)
- Optional persistence to existing SQLite via `ExtractionStore`

## Run state storage

Per run:

- `.batch_runs/<run_id>/state.json`
- `.batch_runs/<run_id>/results.jsonl`
- `.batch_runs/<run_id>/log.txt`
- `.batch_runs/<run_id>/pid` (detached mode only)

`state.json` includes:

- run metadata (start time, mode, config)
- per-worker slot state:
  - current file
  - worker start time
  - elapsed seconds (derived)
- aggregate counters
- terminal status

This file-based state is intentionally lightweight and avoids schema churn in V1.

## CLI Surface

Primary command:

- `finding-extractor-batch run <inputs...>`

Key options:

- `--mode interactive|detached`
- `--workers`
- `--timeout-seconds`
- `--retries`
- `--resume/--no-resume`
- `--output-dir`
- `--suffix`
- `--validate/--no-validate`
- `--store/--no-store`
- `--db-path`
- `--status-interval-seconds`

Status command:

- `finding-extractor-batch status --run-id <id> [--watch]`

## Configuration Model

All batch parameters should resolve with the same precedence used elsewhere:

1. CLI flag
2. Environment variable
3. `.env`
4. `config.toml` (`[ipl]`)
5. Code defaults

Planned settings fields:

- `batch_workers` (`IPL_BATCH_WORKERS`)
- `batch_timeout_seconds` (`IPL_BATCH_TIMEOUT_SECONDS`)
- `batch_retries` (`IPL_BATCH_RETRIES`)
- `batch_status_interval_seconds` (`IPL_BATCH_STATUS_INTERVAL_SECONDS`)
- `batch_output_suffix` (`IPL_BATCH_OUTPUT_SUFFIX`)
- `batch_run_dir` (`IPL_BATCH_RUN_DIR`, default `.batch_runs`)
- `batch_resume` (`IPL_BATCH_RESUME`)

## TaskIQ Positioning

V1 should not call TaskIQ directly.

Future mode can be added as a separate execution backend (API/TaskIQ-backed), while keeping:

1. same high-level CLI contract
2. same status UX
3. same output artifact conventions

That keeps V1 investment reusable without turning this runner into a second broker implementation.

## Failure Semantics

Per file result status:

- `ok`
- `skipped` (resume hit existing output)
- `timeout`
- `failed`

Run exit:

- success only if all files are `ok` or `skipped`
- non-zero if any `failed`/`timeout`

## Implementation Slices

## Slice 1: Runner core

1. Shared async engine
2. Structured per-file result objects
3. Live worker timing data

## Slice 2: Mode support

1. `run --mode interactive`
2. `run --mode detached`
3. `status --run-id` and `--watch`

## Slice 3: Configuration integration

1. Add batch fields to `Settings`
2. Wire env + `config.toml` aliases
3. Update CLI defaults to use settings

## Slice 4: Docs and task wiring

1. `Taskfile` task(s) for common batch workflows
2. usage docs for interactive/detached patterns

## Test Plan

1. Unit tests for config precedence (CLI/env/toml/default)
2. Unit tests for worker state transitions and elapsed-time reporting
3. Integration-style tests with mocked extraction function:
   - mixed success/failure/timeout
   - detached run writes state and returns run id
   - status command reflects active and terminal states

## Acceptance Criteria (V1)

1. A user can run a large folder with bounded workers and per-file timeout
2. A user can run detached and inspect progress later with run id
3. Status output includes elapsed runtime for each active worker
4. No DB schema changes are required
5. No direct TaskIQ usage is introduced in this CLI
