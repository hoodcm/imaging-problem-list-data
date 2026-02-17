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
4. Stream D: post-integration hardening (high/medium review findings from `2dde149`)

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

## Hardening Backlog (From `2dde149` Review)

Priority order for immediate cleanup before next feature phase:

1. Remove dead code and broken task surface:
1. delete unreachable `_code_location()` in `coding_bridge.py`
2. remove/repair stale `matrix:sample` task entry that references deleted script
2. Normalize settings access in task runtime:
1. replace `getattr(settings, ...)` usage in `tasks.py` with typed field access
2. keep compatibility only where explicitly documented as migration shim
3. Coding runtime policy + throughput fixes:
1. `coding_model` fallback policy: if unset, default adjudicator to extraction model
2. remove read-path index serialization lock for DuckDB read-only lookups
3. keep init/teardown locking for shared index lifecycle safety
4. De-duplicate adjudicator/review wiring:
1. collapse duplicate adjudication logic in `coding_agents.py`
2. extract shared configured-agent creation helper (used by extraction/coding/review agents)
3. remove untyped `kwargs: dict` construction in agent factories
5. Test coverage hardening:
1. add unit tests for `coding_agents.py` branches (allowlist, unresolved, invalid id)
2. add unit tests for `extraction_review.py` label allowlist and re-extract decision handling
3. add a targeted regression test for model-id catalog fallback behavior referenced in review
6. Clarify orchestration semantics:
1. document `findings`/`impression`-only extraction gate inline in orchestrator code comments
2. keep canonical stage naming aligned across runtime/docs/UI (`extract_sections`)
