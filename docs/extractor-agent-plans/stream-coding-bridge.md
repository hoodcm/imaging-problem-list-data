# Stream Coding Bridge: Stage 3.5 Baseline OIFM + Location Mapping

Last updated: 2026-02-14
Status: Active

## Stage definition

Stage 3.5 here means: add an initial deterministic coding layer after extraction to provide partial structured coding without blocking extraction completion.

## Scope

1. Deterministic OIFM mapping path:
   1. exact
   2. synonym
   3. curated alias
2. Deterministic location mapping from extracted location fields.
3. Add additive coding payload and unresolved-item reporting.
4. Keep extraction output as source of truth.

## Non-goals

1. Full semantic coding agent (future Stage 7 work).
2. Job failure due solely to coding miss.

## Proposed output additions

1. Per finding:
   1. coding method
   2. provisional confidence
   3. top candidate + alternates
2. Run-level unresolved list with reason categories.

## Dependencies

1. Prefer Stream Reliability Contract alignment for shared warning/status semantics.

## Acceptance criteria

1. Common findings get deterministic partial coding.
2. Unresolved items are explicit and queryable.
3. No extraction regression attributable to coding layer.
