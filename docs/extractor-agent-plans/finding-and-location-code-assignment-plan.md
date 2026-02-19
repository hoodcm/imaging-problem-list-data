# Finding and Location Code Assignment Plan (V2: Parallel + Adjudication)

Last updated: 2026-02-17
Status: In progress

## Goal

Upgrade finding and location code assignment from serial deterministic mapping to parallel coding with deterministic fast path and lightweight LLM adjudication for ambiguous search candidates.

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
2. Keep conservative index access locking for shared DuckDB/index cache safety.
3. Keep lifecycle locking for shared index initialization/teardown.

## Interface Contract

1. `apply_coding(extraction)` remains stable call surface.
2. `apply_coding(extraction)` returns `ReportExtraction` with inline `findings[].coding`.
3. Detached `CodingBridgeResult` payloads are removed from runtime/API/CLI contracts.
4. Shared coding adjudicator model + concurrency remain configurable.

## Test Focus

1. no adjudicator call on deterministic hit
2. adjudicator called only when ambiguous candidates exist
3. bounded parallel execution correctness
4. non-fatal behavior under per-item adjudicator/index errors
5. coding-model fallback to extraction model when `IPL_CODING_MODEL` is unset
6. concurrent coding throughput remains correct under conservative index locks

## Remaining Cleanup

- normalize logging style in coding path modules when touched (`structlog` vs stdlib logger)
- evaluate wrapping reusable index lifecycle in an explicit async context-manager helper (follow-up cleanup, not correctness-critical)
