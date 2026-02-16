# Stream B: Coding Bridge V2 (Parallel + Adjudication)

Last updated: 2026-02-16
Status: In progress

## Goal

Upgrade coding runtime from serial deterministic mapping to parallel coding with deterministic fast path and lightweight LLM adjudication for ambiguous search candidates.

## Scope

1. Keep deterministic coding as first-pass path.
2. Add coding adjudicator sub-agents (shared small model) for:
   1. finding code selection
   2. anatomic location selection
3. Run coding tasks in bounded parallel concurrency.
4. Preserve non-fatal contract: coding failures do not fail extraction jobs.

## Runtime Strategy

1. For each finding, run finding-coding and location-coding work asynchronously.
2. Deterministic hits return immediately (`exact`, `synonym`, confident `search`).
3. If deterministic search returns candidates but confidence is insufficient, call coding adjudicator.
4. Emit method-level counts (`exact`, `synonym`, `search`, `agent`, `unresolved`) for observability.

## Locked Runtime Decisions

1. If `IPL_CODING_MODEL` is unset, adjudication defaults to the extraction model selected for the run.
2. Read-only DuckDB index access is treated as concurrency-safe; per-read global locking should be removed.
3. Keep lifecycle locking only for shared index initialization/teardown.

## Interface Contract

1. `apply_coding(extraction)` remains stable call surface.
2. `CodingBridgeResult` schema remains backward compatible.
3. Add config for shared coding adjudicator model + concurrency.

## Test Focus

1. no adjudicator call on deterministic hit
2. adjudicator called only when ambiguous candidates exist
3. bounded parallel execution correctness
4. non-fatal behavior under per-item adjudicator/index errors
5. coding-model fallback to extraction model when `IPL_CODING_MODEL` is unset
6. concurrent coding throughput path runs without serialized read-lock wrappers
