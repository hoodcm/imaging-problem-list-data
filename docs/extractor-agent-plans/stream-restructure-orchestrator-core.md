# Stream A: Orchestrator Core V2

Last updated: 2026-02-18
Status: In progress

## Goal

Ship one orchestrator runtime path that is chunk-native, parallel, deterministic in assembly, and reviewable via structured status events.

## Scope

1. Replace legacy/modular split with V2 core flow.
2. Build chunk extraction units from findings/impression sections only.
3. Add context-window contract per chunk (prev/next half chunks).
4. Run extraction sub-agents with bounded semaphore concurrency (`default=5`).
5. Add unit-scoped retry and validator-guided targeted re-extraction.
6. Keep deterministic merge/dedupe and stable ordering.

## Required Stage Vocabulary

1. `preflight`
2. `sectionize`
3. `extract_sections`
4. `repair_failed_sections`
5. `merge_dedupe`
6. `validator_review`
7. `validate_output`
8. `apply_coding`
9. `persist`
10. `completed`
11. `completed_with_warnings`
12. `failed`

## Implementation Outline

1. `extraction_orchestrator.py`
   1. define V2 unit models (`chunk_id`, section, target text, context windows)
   2. build units from deterministic section parser + chunker
   3. run bounded async extraction with retries
   4. merge/dedupe deterministically
   5. run validator and targeted retry pass
2. `extraction_agent.py`
   1. add chunk-focused prompt contract with context channels
   2. maintain verbatim validation against target chunk only
3. `tasks.py`
   1. wire V2 orchestrator parameters and status event emission

## Test Focus

1. chunk unit generation and context windows
2. bounded concurrency and retry behavior
3. deterministic merge order under async completion variance
4. validator-driven targeted re-extraction behavior

## Remaining Cleanup In This Stream

- replace broad callable aliases with explicit `Protocol` signatures:
- extraction callable
- validator-review callable
- normalize callback/helper naming:
- keep one canonical status-callback type alias
- converge `_emit_stage`/`_emit` helper usage
- remove minor helper duplication:
- reuse semantic chunking single-chunk helper instead of local passthrough helper
- dedupe `_review_chunks` callback wiring between worker/runtime where possible
- move provider-specific reasoning workaround out of runtime and into provider settings resolution

## Completion Plan (Next Execution Order)

### Phase 1 (land now)

1. Wire orchestrator chunk sub-agent calls to dedicated chunk prompt/schema (`ChunkExtraction`).
2. Keep deterministic sectioning/chunking contract unchanged.
3. Preserve existing merge/dedupe/coding/review stage contracts.
4. Confirm worker/CLI runtime uses the same chunk sub-agent path.

### Phase 2

1. Add single-pass exam metadata extraction strategy (deterministic/LLM policy decision).
2. Remove remaining full-report extraction prompt dependency from orchestrator flow.
3. Add focused runtime tests around chunk prompt/context wiring.

### Phase 3

1. Tune chunk example selection policy (fixed deterministic subset vs dynamic selection).
2. Finalize docs for operator-facing model choices and chunk-agent behavior.
3. Re-run smoke + integration checks and update `docs/DEV_LOG.md` evidence.
