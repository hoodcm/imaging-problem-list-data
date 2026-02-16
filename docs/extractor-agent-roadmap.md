# Extractor Agent Roadmap (V2)

Last updated: 2026-02-16
Owner: extractor team
Status: Active

## Canonical Priority

The active priority is **Chunk-Scoped Orchestrator V2**.
All previous stage/slice hardening work is treated as baseline context, not current execution guidance.

## Active Workstreams (Current Cycle)

1. Stream A: orchestrator V2 core (sectionize -> chunk extraction -> merge -> validator rework)
2. Stream B: coding sub-agent runtime (parallel deterministic + adjudication)
3. Stream C: structured status events + API/UI + Logfire instrumentation

## Merge Strategy

1. Merge Stream A first (defines core runtime and interfaces).
2. Rebase Streams B/C onto Stream A tip.
3. Merge Stream B second.
4. Merge Stream C last.

## Dependency Notes

1. Stream B depends on final extraction/chunk unit shape from Stream A.
2. Stream C depends on final stage/event model from Stream A and coding event hooks from Stream B.

## Completed Baseline (Historical)

1. reliability contract hardening
2. provider fail-fast + fallback/runtime limits
3. chunking foundation
4. coding bridge baseline
5. status-stage UI first pass

Historical docs remain in `docs/extractor-agent-plans/` for reference.
