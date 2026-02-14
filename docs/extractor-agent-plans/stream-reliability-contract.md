# Stream Reliability Contract: Stage 3 Strict/Lenient + Warning Lifecycle

Last updated: 2026-02-14
Status: Active

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

## Dependencies

1. Align with Stream Coding Bridge if coding emits warnings in the same payload family.

## Acceptance criteria

1. New status lifecycle works end-to-end and remains backward compatible.
2. API responses expose warning payload deterministically.
3. CLI/batch behavior matches API behavior for same mode.
4. Tests cover state transitions and payload schema.
