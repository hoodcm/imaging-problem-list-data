# Extractor Agent Roadmap

Last updated: 2026-02-14
Owner: extractor team
Status: Active, continuously updated

## Quick Abstract: Current Streams and Stages

This is the canonical index for extractor-agent planning.

### Active streams (forward-looking)

1. **Stream Eval Closure (Stage 3: report-section improvements closure)**
   What this stream does: verify the already-implemented section parsing + source tracking changes with explicit before/after eval evidence.
   Plan doc: `docs/extractor-agent-plans/stream-eval-closure.md`
2. **Stream Reliability Contract (Stage 3: strict/lenient + warnings)**
   What this stream does: define deterministic partial-success behavior, warning payloads, and warning-terminal status.
   Plan doc: `docs/extractor-agent-plans/stream-reliability-contract.md`
3. **Stream Coding Bridge (Stage 3.5: baseline OIFM/location coding)**
   What this stream does: add non-blocking deterministic coding output on top of extracted findings.
   Plan doc: `docs/extractor-agent-plans/stream-coding-bridge.md`
4. **Stream Provider Expansion (Stage 5: provider/model capability work)**
   What this stream does: split provider-specific settings from `agent.py` and expand model capability/discovery work.
   Plan doc: `docs/extractor-agent-plans/stream-provider-expansion.md`

### Completed stages (reference)

1. **Stage 0: Reasoning + usage contracts hardening**
   Done doc: `docs/extractor-agent-plans/stage0_reasoning-and-usage-contracts_done.md`
2. **Stage 1: In-flight status messages for jobs/CLI**
   Done doc: `docs/extractor-agent-plans/stage1_in-flight-progress-status_done.md`
3. **Stage 1.5: Agent-internal status callback**
   Done doc: `docs/extractor-agent-plans/stage1_5_agent-internal-status-callback_done.md`
4. **Stage 2: Eval harness, datasets, matching, native reporting**
   Done doc: `docs/extractor-agent-plans/stage2_eval-harness-and-reporting_done.md`
5. **Stage 3 (Phases 0-2): Prompt refactor + schema guidance updates**
   Done doc: `docs/extractor-agent-plans/stage3_prompt-refactor-and-guidance-phases0-2_done.md`

## Current State Summary

1. Core extraction/eval infrastructure is in place and stable (`task lint`, `task test`, `task db:check` passing on unified `dev`).
2. Stage 3 section parsing/source tracking implementation is merged, but formal quality closure still requires recorded eval evidence.
3. The next practical work can run in parallel across the four active streams above.

## Stream Order and Dependencies

1. Stream Eval Closure should complete before marking Stage 3 fully complete.
2. Stream Reliability Contract and Stream Coding Bridge can run in parallel; Stream Coding Bridge should rebase on Stream Reliability Contract if warning/status contracts affect coding outputs.
3. Stream Provider Expansion is mostly independent and can run in parallel if it avoids unnecessary API/status contract changes.

## Canonical Planning Directory

All extractor-agent planning docs live in:
1. `docs/extractor-agent-plans/`

## Idea Backlog (Not Yet Streamed)

These are useful ideas but not currently committed as active streams:

1. Section-aware verbatim validation (quote must appear in claimed section when sections are known).
2. Section-specific coverage metrics (what report sections produced findings vs none).
3. Matching-confidence meta-evaluator (gap between best and second-best match).
4. Evaluator treatment of unmatched findings in location/attribute/presence dimensions.
5. Optional `job_events` audit table and SSE/WebSocket streaming layer.
6. Stage 4B DuckDB retrieval path only if file-based selection cannot hit quality/maintenance targets.
7. Stage 6 chunked sub-agent pipeline only if long-report failure/latency metrics justify complexity.
