# Extractor Agent Roadmap

Last updated: 2026-02-14
Owner: extractor team
Status: Active, parallel execution

## Quick Abstract

This is the canonical index for extractor-agent planning and stream coordination.

## Active Parallel Streams (current cycle)

1. **Stream A: Restructure Orchestrator Core**
   What it does: introduces modular orchestration boundaries and canonical stage/status contract wiring.
   Plan doc: `docs/extractor-agent-plans/stream-restructure-orchestrator-core.md`
2. **Stream B: Provider Fail-Fast Hardening**
   What it does: enforces effective reasoning validation and provider compatibility at preflight.
   Plan doc: `docs/extractor-agent-plans/stream-provider-failfast-hardening.md`
3. **Stream C: Coding Runtime Hardening**
   What it does: optimizes coding bridge index lifecycle and region-aware location matching.
   Plan doc: `docs/extractor-agent-plans/stream-coding-runtime-hardening.md`
4. **Stream D: Coding API/UI Contract**
   What it does: exposes coding payload in API/store and renders coding/progress in extractor UI.
   Plan doc: `docs/extractor-agent-plans/stream-coding-api-ui-contract.md`

## Merge Order and Dependencies

1. Stream B -> Stream C -> Stream A -> Stream D.
2. Stream D rebases after Stream A merges if stage/status fields change.
3. Stream A rebases after B/C merge to consume final fail-fast and coding runtime behavior.

## Follow-on Streams (queued after current cycle)

1. **Stream Eval Closure (Stage 3 evidence closure)**
   Plan doc: `docs/extractor-agent-plans/stream-eval-closure.md`
2. **Stream Reliability Contract (strict/lenient + warnings lifecycle)**
   Plan doc: `docs/extractor-agent-plans/stream-reliability-contract.md`
3. **Stream Provider Expansion (catalog/capability/presets follow-up)**
   Plan doc: `docs/extractor-agent-plans/stream-provider-expansion.md`
4. **Stream Coding Bridge (stage 7 agent-based coding follow-up)**
   Plan doc: `docs/extractor-agent-plans/stream-coding-bridge.md`

## Completed Stage Docs

1. `docs/extractor-agent-plans/stage0_reasoning-and-usage-contracts_done.md`
2. `docs/extractor-agent-plans/stage1_in-flight-progress-status_done.md`
3. `docs/extractor-agent-plans/stage1_5_agent-internal-status-callback_done.md`
4. `docs/extractor-agent-plans/stage2_eval-harness-and-reporting_done.md`
5. `docs/extractor-agent-plans/stage3_prompt-refactor-and-guidance-phases0-2_done.md`

## Operating Notes

1. `docs/agent_restructuring.md` is the master execution plan for this cycle.
2. Each stream doc must remain focused and decision-complete for that stream only.
3. Keep `docs/DEV_LOG.md` entries concise and milestone-oriented.
