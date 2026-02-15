# Extractor Agent Roadmap

Last updated: 2026-02-15 (next push reset)
Owner: extractor team
Status: Active, next push setup

## Quick Abstract

This is the canonical index for extractor-agent planning and stream coordination.

## Active Streams (next push)

1. **Stream 1: Modular Pipeline Rollout Slice 2**
   What it does: finalizes modular runtime behavior (observability + reliability reconciliation + rollout criteria).
   Plan doc: `docs/extractor-agent-plans/stream-restructure-orchestrator-core.md`
2. **Stream 2: Provider Expansion Slice 1**
   What it does: expands provider/catalog capability metadata and policy-safe presets.
   Plan doc: `docs/extractor-agent-plans/stream-provider-expansion.md`
3. **Stream 3: Coding Bridge Follow-on Slice 1**
   What it does: advances coding bridge unresolved-handling and Stage 7 agent-handoff readiness.
   Plan doc: `docs/extractor-agent-plans/stream-coding-bridge.md`

## Merge Order and Dependencies

1. Stream 1 -> Stream 2 -> Stream 3.
2. Stream 2 rebases after Stream 1 if shared config/policy files changed.
3. Stream 3 rebases after Stream 1 if task/runtime contract or stage semantics changed.

## Integrated Streams (previous cycle now on `dev`)

1. Stream B: Provider Fail-Fast Hardening
2. Stream C: Coding Runtime Hardening
3. Stream A: Restructure Orchestrator Core (slice 1)
4. Stream D: Coding API/UI Contract
5. Stream Reliability Contract (backend + UI)
6. Stream Eval Closure (Stage 3 evidence)

## Completed Stage Docs

1. `docs/extractor-agent-plans/stage0_reasoning-and-usage-contracts_done.md`
2. `docs/extractor-agent-plans/stage1_in-flight-progress-status_done.md`
3. `docs/extractor-agent-plans/stage1_5_agent-internal-status-callback_done.md`
4. `docs/extractor-agent-plans/stage2_eval-harness-and-reporting_done.md`
5. `docs/extractor-agent-plans/stage3_prompt-refactor-and-guidance-phases0-2_done.md`
6. `docs/extractor-agent-plans/stream-eval-closure.md`
7. `docs/extractor-agent-plans/stream-reliability-contract.md`

## Operating Notes

1. `docs/agent_restructuring.md` is the master execution plan for this cycle.
2. Each stream doc must remain focused and decision-complete for that stream only.
3. Keep `docs/DEV_LOG.md` entries concise and milestone-oriented.
