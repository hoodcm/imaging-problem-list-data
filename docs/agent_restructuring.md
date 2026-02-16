# Agent Restructuring Plan (V2)

Last updated: 2026-02-16
Status: Active (Phase 0 complete, Phase 1 in implementation)

## Why We Are Changing

The extraction runtime still needs a tighter, more parallel architecture at chunk granularity.
We are moving to a single V2 orchestration path centered on:

1. deterministic section parsing
2. findings/impression chunk-scoped extraction units
3. bounded async parallel sub-agent execution
4. deterministic merge/dedupe
5. validator-guided targeted re-extraction
6. parallel coding with deterministic fast path + LLM adjudication for ambiguous search candidates
7. structured status events + Logfire stage instrumentation

## Locked Decisions

1. Section split remains deterministic and stays the first step.
2. Only `findings` and `impression` are extraction scopes.
3. Chunk context is advisory only:
   1. target chunk is the only extractable text
   2. preceding/following half-chunks are context
4. Sub-agent extraction runs in bounded parallelism with default max concurrency `5`.
5. Retry remains unit-scoped; no whole-report retry by default.
6. Coding runs in parallel and remains non-fatal for overall extraction completion.
7. Validator review is one pass with at most one targeted re-extraction cycle.
8. Status contract moves to structured events, with legacy string compatibility during transition.

## V2 Runtime Flow

1. `preflight`: load report, model/runtime validation, initialize run identifiers.
2. `sectionize`: parse section structure, isolate findings/impression units, chunk selected sections.
3. `extract_chunks`: run chunk extraction sub-agents with bounded semaphore and unit retries.
4. `merge_dedupe`: deterministic assembly + dedupe across units.
5. `coding`: parallel finding/anatomic coding with deterministic-first strategy and optional LLM adjudication.
6. `validator_review`: LLM review nominates chunks for targeted re-extraction when needed.
7. `persist`: store extraction, validation, coding, usage, diagnostics.
8. `completed` / `completed_with_warnings` / `failed`.

## In Scope (Current Phase)

1. Replace legacy/modular branch split with one V2 orchestration path.
2. Add chunk work-unit context contract and prompt scaffolding.
3. Add structured status events and API/UI surface support.
4. Add coding adjudicator sub-agent module and parallel runtime wiring.
5. Add Logfire instrumentation at orchestrator stage boundaries.

## Not In Scope (Current Phase)

1. New database tables for per-chunk artifacts.
2. RadSlumberChunker.
3. Major API-breaking changes.

## Acceptance Criteria

1. End-to-end extraction executes only findings/impression chunks in parallel.
2. Context windows are provided for chunk units, but extraction is constrained to target chunk evidence.
3. Coding stage runs in parallel and returns quickly on deterministic hits.
4. Validator-guided targeted re-extraction is functional and bounded.
5. Structured status events are available to API/UI and mirrored in logs.
6. V2 tests and smoke runs are green.
