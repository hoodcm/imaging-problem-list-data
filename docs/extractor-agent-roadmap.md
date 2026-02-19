# Extractor Agent Roadmap (V2)

Last updated: 2026-02-18
Owner: extractor team
Status: Active

## Canonical Priority

The active priority is **Chunk-Scoped Orchestrator V2**.
All prior hardening work is treated as baseline context, not current execution guidance.

## Backlog Tracking

Canonical centralized backlog docs:

1. `docs/pending-refactoring.md` (near-term refactor/cleanup queue)
2. `docs/future-improvements.md` (longer-horizon improvements)

## Active Work Areas (Current Cycle)

1. Orchestrator core (sectionize -> chunk extraction -> merge -> validator rework)
2. Finding and location code assignment (parallel deterministic + adjudication)
3. Structured status events + API/UI + Logfire instrumentation
4. Post-integration hardening (high/medium review findings from `2dde149`)

## Integration Order

1. Land orchestrator core first (defines core runtime and interfaces).
2. Rebase coding and status-event work onto orchestrator core tip.
3. Land finding and location code assignment next.
4. Land status-event/API/UI work last.

## Dependency Notes

1. Finding and location code assignment depends on final extraction/chunk unit shape from orchestrator core.
2. Status-event/API/UI work depends on final stage/event model from orchestrator core and coding event hooks.

## Completed Baseline (Historical)

1. reliability contract hardening
2. provider fail-fast + fallback/runtime limits
3. chunking foundation
4. finding/location coding baseline
5. status-stage UI first pass
6. chunk sub-agent wiring (dedicated `ChunkExtraction` schema)
7. orchestrator next-phase: exam-info sub-agent, coding context upgrade, validator feedback, per-piece timeouts

Historical docs remain in `docs/extractor-agent-plans/` for reference.

## Hardening Backlog (From `2dde149` Review)

Status summary:

- resolved:
- remove stale `matrix:sample` task reference
- replace `getattr(settings, ...)` with typed settings access in runtime paths
- set coding-model fallback to extraction model when `IPL_CODING_MODEL` is unset
- align canonical stage naming (`extract_sections`) across runtime/docs/UI
- superseded by current design decisions:
- remove read-path index serialization lock
- keep compatibility shims as a default strategy
- still open:
- remove any remaining unreachable/dead coding-path helpers
- de-duplicate adjudicator/review wiring and untyped kwargs construction
- expand targeted tests for coding/review/model-catalog fallback behavior
- improve inline orchestrator comments for findings/impression extraction gate semantics

## Consolidated Cleanup Backlog (Supersedes `architecture_restructure_cleanup.md`)

Resolved in current branch:

- provider detection deduplicated to canonical `model_policy.provider_from_model_id`
- retryable provider error logic centralized in `model_resilience`
- runtime/orchestrator callable aliases deduplicated
- smoke runner now treats `completed_with_warnings` as terminal success

Open items (fix-next):

- strengthen pipeline callable typing:
- replace broad `Callable[..., ...]` with explicit `Protocol` call signatures
- improve consistency in orchestration/runtime helpers:
- normalize status callback naming to one canonical alias
- unify `_emit_stage`/`_emit` helper pattern where practical
- relocate provider-specific reasoning workaround:
- move OpenAI gpt-5 `"none" -> "minimal"` handling from runtime into provider settings layer

Open items (later, opportunistic):

- logging style consistency (`structlog` vs stdlib `logging`) for touched modules
- helper dedupe: orchestrator passthrough chunk helper vs semantic chunking single-chunk helper
- dedupe review-callback wiring between `tasks.py` and `extraction_runtime.py`
- reduce repetitive config alias boilerplate where safe
- evaluate replacing manual coding-index `__aenter__/__aexit__` lifecycle calls with an explicit async context-manager wrapper

Execution mapping:

- Orchestrator core plan (`orchestrator-core-plan.md`):
- callable protocols
- status callback + emit-helper normalization
- passthrough/review callback dedupe
- provider workaround relocation
- Finding and location code assignment plan (`finding-and-location-code-assignment-plan.md`):
- logging normalization for coding path
- optional index lifecycle wrapper cleanup
