# Stream Reliability Contract: Stage 3 Strict/Lenient + Warning Lifecycle

Last updated: 2026-02-15
Status: Implemented (backend/API contract + UI surface)

## Stage definition

Stage 3 reliability work means deterministic behavior when validation issues occur: strict mode failure vs lenient mode completion with warnings.

## Scope

1. Define strict and lenient validation mode behavior.
2. Add machine-readable warning payload (dropped counts + reason categories).
3. Add terminal `completed_with_warnings` status and propagate through store/API/UI/CLI.
4. Ensure behavior is deterministic and test-covered.

## Core contract

1. `strict`:
   1. critical validation errors fail the job.
2. `lenient`:
   1. persist valid findings
   2. drop invalid findings/spans
   3. return warnings payload
   4. terminal status `completed_with_warnings`.

## Implemented backend/API contract (v1)

1. Request contract:
   1. `POST /api/reports/{id}/extract` accepts `reliability_mode` with values:
      1. `strict` (default)
      2. `lenient`
2. Terminal status contract:
   1. `completed` for warning-free successful jobs
   2. `completed_with_warnings` for successful jobs with deterministic warnings payload
   3. `failed` for hard failures (including strict-mode validation failure)
3. Warning payload schema (`jobs.warning_payload`):
   1. `schema_version`: `"v1"`
   2. `reliability_mode`: `"strict" | "lenient"`
   3. `reason_categories`: ordered subset of:
      1. `validation_failed`
      2. `verbatim_mismatch`
      3. `coverage_gap`
   4. `dropped_findings_count`: integer
   5. `dropped_non_finding_count`: integer
   6. `validation_error_count`: integer
   7. `coverage_warning_count`: integer
4. Strict semantics:
   1. if validation errors are present, fail with `extraction_failed:validation_failed`
   2. include `warning_payload` on failed job for deterministic client handling
5. Lenient semantics:
   1. invalid spans are dropped deterministically before persistence
   2. job completes with `completed_with_warnings` and `warning_payload`

## Implemented UI surface

1. Extracting status view treats `completed_with_warnings` as terminal success.
2. Extraction detail renders a warning banner when `validation_result` contains issues.
3. UI mock mode supports warnings flow for deterministic Playwright coverage.

## Dependencies

1. Align with Stream Coding Bridge if coding emits warnings in the same payload family.

## Acceptance criteria

1. New status lifecycle works end-to-end and remains backward compatible.
2. API responses expose warning payload deterministically.
3. CLI/batch behavior matches API behavior for same mode.
4. Tests cover state transitions and payload schema.
