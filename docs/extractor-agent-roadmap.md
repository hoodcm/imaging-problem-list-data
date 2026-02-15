# Extractor Agent Roadmap

Last updated: 2026-02-15 (post-integration hardening complete)
Owner: extractor team
Status: Active, integrated streams + hardening sequence complete

## Quick Abstract

This is the canonical index for extractor-agent planning and stream coordination.

## Hardening Sequence (Completed)

1. **Change Set 1: Reliability Semantics Clarification** ✓
   What it does: finalizes strict-mode semantics for unrecovered section failures and warning payload accounting.
   Plan docs:
   1. `docs/extractor-agent-plans/stream-reliability-contract.md`
   2. `docs/extractor-agent-plans/stream-restructure-orchestrator-core.md`
2. **Change Set 2: Effective Reasoning Canonicalization** ✓
   What it does: normalizes runtime reasoning resolution and persistence across task/CLI paths.
   Plan doc: `docs/extractor-agent-plans/stream-provider-expansion.md`
3. **Change Set 3: Stage Status UX Closure** ✓
   What it does: aligns extractor UI stage rendering with canonical `[stage:*]` worker status format.
   Plan doc: `docs/extractor-agent-plans/stream-restructure-orchestrator-core.md`
4. **Change Set 4: Coding Index Lifecycle + Concurrency Hardening** ✓
   What it does: adds explicit lifecycle handling and concurrency hardening for reusable coding indexes.
   Plan doc: `docs/extractor-agent-plans/stream-coding-bridge.md`

## Merge Order and Dependencies (Executed)

1. Change Set 1 -> Change Set 2 -> Change Set 3 -> Change Set 4.
2. Change Set 2 depends on finalized reliability warning semantics where payload fields are shared.
3. Change Set 3 depends on stable stage/status grammar from Change Set 1.
4. Change Set 4 should run after Change Set 1 to avoid churn in task/runtime contracts.

## Integrated Streams (previous cycle now on `dev`)

1. Stream B: Provider Fail-Fast Hardening
2. Stream C: Coding Runtime Hardening
3. Stream A: Restructure Orchestrator Core (slices 1 + 2)
4. Stream D: Coding API/UI Contract
5. Stream Reliability Contract (backend + UI)
6. Stream Provider Expansion Slice 1.2 (capability metadata + presets)
7. Stream Coding Bridge Follow-on Slice 1 (unresolved fallback hardening)
8. Stream Eval Closure (Stage 3 evidence)

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
