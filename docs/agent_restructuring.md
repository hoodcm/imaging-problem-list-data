# Agent Restructuring Plan

Last updated: 2026-02-15 (post-integration reset)
Status: Active (next push kickoff)

## Why We Are Changing

The current extractor flow is too monolithic for latency, progress visibility, and focused retries. We are moving to a modular, provider-agnostic architecture where retries and diagnostics happen at small unit boundaries.

## Locked Decisions

1. Orchestration approach: PydanticAI workers + deterministic Python orchestration.
2. Work mode: parallel streams in separate worktrees.
3. Coding scope: coding is included in Phase 1 API/UI contract work.
4. Retry principle: retry failed units only, not whole reports by default.
5. Reliability contract is now first-class (`strict` / `lenient` + `completed_with_warnings`).

## Primary Goals

1. Get extraction runtime into fractions of a minute in normal cases.
2. Provide stage-level progress and unit-level progress.
3. Fail fast for invalid runtime/provider/reasoning config.
4. Keep provider switching practical (hosted + open-weight backends).
5. Expose coding outputs in API/UI without making coding failures job-fatal.

## Canonical Stage Vocabulary

1. `queued`
2. `preflight`
3. `sectionize`
4. `extract_sections`
5. `merge_dedupe`
6. `repair_failed_sections`
7. `validate_output`
8. `apply_coding`
9. `persist`
10. `completed` / `completed_with_warnings` / `failed`

## Current State (Integrated on `dev`)

Completed and integrated:

1. Stream B: provider fail-fast hardening
2. Stream C: coding runtime hardening
3. Stream A: orchestrator core + modular behavior slice 1
4. Stream D: coding API/UI contract
5. Follow-on reliability contract (backend + UI)
6. Follow-on Stage 3 eval closure evidence

## Next Push Streams

### Stream 1 (this worktree): Modular Pipeline Rollout Slice 2

- Plan: `docs/extractor-agent-plans/stream-restructure-orchestrator-core.md`
- Worktree: `/Users/talkasab/repos/imaging-problem-list`
- Branch: `feature/modular-pipeline-rollout-slice2`
- Focus:
  1. reconcile reliability strict/lenient behavior with unit-level failures
  2. add stage/unit observability counters and diagnostics
  3. define rollout criteria for safely enabling modular mode beyond default-off

### Stream 2 (`-agent`): Provider Expansion Slice 1

- Plan: `docs/extractor-agent-plans/stream-provider-expansion.md`
- Worktree: `/Users/talkasab/repos/imaging-problem-list-agent`
- Branch: `feature/provider-expansion-slice1`
- Focus:
  1. model catalog/capability metadata expansion
  2. safe presets/capability policy alignment
  3. keep fail-fast behavior intact

### Stream 3 (`-provider`): Coding Bridge Follow-on Slice 1

- Plan: `docs/extractor-agent-plans/stream-coding-bridge.md`
- Worktree: `/Users/talkasab/repos/imaging-problem-list-provider`
- Branch: `feature/coding-bridge-followon-slice1`
- Focus:
  1. coding bridge unresolved handling and deterministic fallback quality
  2. stage-7 prep for agent-assisted coding
  3. preserve non-fatal coding behavior at task level

## Merge Order

1. Stream 1
2. Stream 2
3. Stream 3

Rationale: Stream 1 finalizes the execution/runtime contract first; Streams 2 and 3 then layer capability expansion work on top of stabilized orchestration/reliability behavior.

## Coordination Rules

1. Stream 1 owns stage/status/runtime orchestration behavior and rollout controls.
2. Stream 2 owns provider/catalog capability expansion and policy consistency.
3. Stream 3 owns coding bridge internals and agent-bridge handoff design.
4. Rebase before merge when shared files overlap (`tasks.py`, `config.py`, `model_catalog.py`, `coding_bridge.py`, docs).

## Validation Requirements

Per stream minimum:

1. Stream 1: `uv run pytest tests/test_tasks.py tests/test_extraction_orchestrator.py -q`
2. Stream 2: `uv run pytest tests/test_model_catalog.py tests/test_model_policy.py tests/test_config.py tests/test_cli.py tests/test_api.py -q`
3. Stream 3: `uv run pytest tests/test_coding_bridge.py tests/test_tasks.py tests/test_store.py -q`

Final integration on `dev`:

1. `task lint`
2. `task test`

## Kickoff Outputs (required)

1. Stream plan docs updated with concrete run state, risks, and remaining work.
2. Concise `docs/DEV_LOG.md` entry per stream with validation evidence.
3. Integration-ready branch tips for staged merge order.
