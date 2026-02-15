# Stream A: Restructure Orchestrator Core

Last updated: 2026-02-15
Status: Implemented (behavior slices 1-3 shipped; hardening complete)
Owner/worktree: `/Users/talkasab/repos/imaging-problem-list` (`feature/modular-pipeline-rollout-slice2`)

## Goal

Roll out modular extraction orchestration in safe slices:
1. canonical stage boundaries/status contract
2. section-aware bounded parallel extraction
3. targeted failed-unit repair (no whole-report retry by default)

## In scope

1. Orchestrator module with explicit stage boundaries and deterministic sequencing.
2. Worker routing through orchestrator entrypoint.
3. Canonical stage vocabulary in worker status messages.
4. Section-unit extraction with bounded concurrency.
5. Targeted retry of failed section units.
6. Safety guard to keep legacy behavior default.
7. Test coverage for stage status, bounded parallelism, and targeted repair.

## Out of scope

1. Provider fail-fast policy redesign.
2. Coding bridge runtime internals.
3. API/UI schema changes.
4. Agent-based coding/reliability-contract follow-on streams.

## Canonical stage vocabulary

1. `preflight`
2. `sectionize`
3. `extract_sections`
4. `merge_dedupe`
5. `repair_failed_sections`
6. `validate_output`
7. `apply_coding`
8. `persist`
9. `completed`
10. `failed`

## Implementation plan

1. Add `src/finding_extractor/extraction_orchestrator.py`:
   1. define stage execution helpers
   2. define orchestration entrypoint consumed by tasks
   3. add section-unit execution path behind rollout guard
2. Update `src/finding_extractor/tasks.py` to pass rollout/config controls.
3. Add settings toggles for modular rollout and bounded section concurrency.
4. Keep legacy single-pass behavior as the default mode.

## Files expected to change

1. `src/finding_extractor/extraction_orchestrator.py`
2. `src/finding_extractor/tasks.py`
3. `src/finding_extractor/config.py`
4. `tests/test_tasks.py`
5. `tests/test_extraction_orchestrator.py`

## Test plan

1. `uv run pytest tests/test_tasks.py -q`
2. `uv run pytest tests/test_extraction_orchestrator.py -q`
3. `task lint`
4. `task test`

## Acceptance criteria

1. Worker status messages use canonical stage labels.
2. Modular mode executes section units with bounded concurrency.
3. Repair mode retries failed units without whole-report retries by default.
4. Legacy behavior remains default unless modular mode is enabled.
5. Stream test scope is green.

## Progress

### 2026-02-14: Orchestrator skeleton + canonical stage status wiring

Shipped:

1. Added `src/finding_extractor/extraction_orchestrator.py` with:
   1. `run_orchestrated_extraction(...)` structure-first orchestration entrypoint.
   2. `format_stage_status(...)` for parseable stage status messages.
   3. explicit stage sequencing for:
      - `sectionize`
      - `extract_sections`
      - `merge_dedupe`
      - `repair_failed_sections`
      - `validate_output`
      - `apply_coding` (when enabled)
2. Updated `src/finding_extractor/tasks.py` to:
   1. route extraction flow through orchestrator entrypoint
   2. emit canonical preflight/persist/completed/failed stage messages
   3. preserve existing persistence and completion/failure semantics
3. Added tests in `tests/test_tasks.py` for:
   1. canonical stage emission order on success
   2. failed-stage status emission on exceptions

Validation:

1. `uv run pytest tests/test_tasks.py -q` -> 10 passed
2. `uv run ruff check src/finding_extractor/extraction_orchestrator.py src/finding_extractor/tasks.py tests/test_tasks.py` -> clean

### 2026-02-15: Behavior slice 1 (section parallel + targeted repair)

Shipped:

1. Extended `run_orchestrated_extraction(...)` with a modular path (guarded by settings):
   1. sectionized extraction units from detected report sections (`findings`/`impression` priority)
   2. bounded concurrency execution (`section_max_concurrency`)
   3. targeted retry loop for failed units only (`section_repair_attempts`)
2. Added deterministic merge/dedupe pass across section outputs:
   1. finding-level dedupe across units
   2. source section reconciliation (`findings` + `impression` -> `both`)
   3. usage aggregation across successful units
3. Added rollout controls in config:
   1. `IPL_MODULAR_PIPELINE_ENABLED` (default `false`)
   2. `IPL_MODULAR_PIPELINE_MAX_CONCURRENCY` (default `2`)
   3. `IPL_MODULAR_PIPELINE_REPAIR_ATTEMPTS` (default `1`)
4. Updated task wiring to pass modular settings through orchestrator.
5. Added tests:
   1. `tests/test_extraction_orchestrator.py` (bounded concurrency, targeted retry, cross-section dedupe/source merge)
   2. `tests/test_tasks.py` task-level modular retry wiring coverage
6. Post-review correctness fix:
   1. sort successful section outcomes by `unit.index` before merge
   2. prevents transient-failure-dependent drift in finding order and `exam_info` selection

Validation:

1. `uv run pytest tests/test_tasks.py -q` -> 12 passed
2. `uv run pytest tests/test_extraction_orchestrator.py -q` -> 4 passed
3. `task lint` -> clean (ruff + ty + web + db check)
4. `task test` -> 432 passed

### 2026-02-15: Behavior slice 2 (reliability reconciliation + stage/unit diagnostics)

Shipped:

1. Extended orchestrator output contract with machine-parseable modular diagnostics:
   1. `PipelineDiagnostics` on `OrchestratedExtractionResult`
   2. totals for unit count/attempt count, initial failures, repaired count, and remaining failed units
   3. deterministic failed unit labels and terminal error types
2. Added actionable stage/unit status diagnostics in modular mode:
   1. `extract_sections` summary status with total/success/failure/attempt counters
   2. per-repair-attempt `start` and `summary` statuses
   3. repair exhaustion status including remaining failed unit labels and error classes
3. Reconciled strict/lenient reliability behavior with section-unit failures:
   1. lenient mode now completes with warnings when modular repair exhausts with failed units
   2. strict mode now fails deterministically when failed units remain after targeted repair
   3. warning payload includes `coverage_gap` category and deterministic coverage count derived from modular diagnostics
4. Preserved rollout safety controls and retry scope:
   1. modular mode remains explicit and default-off
   2. retries stay scoped to failed units only (no whole-report retry)
5. Added focused coverage for slice-2 runtime behavior:
   1. `tests/test_extraction_orchestrator.py` diagnostics assertions for summary counters and repair exhaustion details
   2. `tests/test_tasks.py` strict/lenient modular remaining-failure contract tests

Validation:

1. `uv run pytest tests/test_tasks.py tests/test_extraction_orchestrator.py -q` -> 21 passed
2. `task lint` -> clean
3. `task test` -> 440 passed

### 2026-02-15: Behavior slice 3 (contract + UX hardening) ✓

Shipped:

1. Finalized strict-mode semantics for unrecovered section failures:
   1. dedicated public error `extraction_failed:section_failures_remaining`
   2. strict validation failures remain `extraction_failed:validation_failed`
2. Extended warning payload v1 additively with section failure accounting:
   1. `section_failure_count` added
   2. existing coverage fields/categories preserved for compatibility
3. Closed stage status UX loop in extractor UI:
   1. parse canonical `[stage:<name>] detail` shape
   2. render stable stage label + concise detail
   3. retain legacy plain-text status compatibility
4. Added focused coverage:
   1. strict/lenient contract tests in `tests/test_tasks.py` + `tests/test_api.py`
   2. stage-status UI parsing tests in `tests/test_ui.py`

Validation:

1. `uv run pytest tests/test_tasks.py tests/test_api.py tests/test_ui.py -q` -> green
2. `task lint` -> clean
3. `task test` -> 472 passed

## Remaining

1. Evaluate rollout defaults and guard behavior in integration environments before turning modular mode on by default.
2. Add metric sinks/alerts for new diagnostics counters and strict section-failure terminals.
3. Tune operator-facing stage detail copy after integration usage feedback.
