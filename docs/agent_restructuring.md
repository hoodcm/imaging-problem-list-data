# Agent Restructuring Plan

Last updated: 2026-02-15 (post-integration hardening complete)
Status: Active (post-integration hardening complete for Change Sets 1-4)

## Why We Are Changing

The current extractor flow is too monolithic for latency, progress visibility, and focused retries. We are moving to a modular, provider-agnostic architecture where retries and diagnostics happen at small unit boundaries.

## Locked Decisions

1. Orchestration approach: PydanticAI workers + deterministic Python orchestration.
2. Work mode: parallel streams in separate worktrees.
3. Coding scope: coding is included in Phase 1 API/UI contract work.
4. Retry principle: retry failed units only, not whole reports by default.
5. Reliability contract is now first-class (`strict` / `lenient` + `completed_with_warnings`).
6. Strict-mode unrecovered modular section failures use dedicated public error
   `extraction_failed:section_failures_remaining` (not `validation_failed`).
7. Warning payload v1 is extended additively with `section_failure_count` while
   preserving existing fields for compatibility.

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
3. Stream A: orchestrator core + modular behavior slices 1 and 2
4. Stream D: coding API/UI contract
5. Follow-on reliability contract (backend + UI)
6. Stream 2: provider expansion slice 1.2 (capability metadata + presets)
7. Stream 3: coding bridge follow-on slice 1 (unresolved/fallback hardening)
8. Follow-on Stage 3 eval closure evidence

## Post-Integration Hardening Change Sets

### Change Set 1: Reliability Semantics Clarification

Plan docs:
1. `docs/extractor-agent-plans/stream-reliability-contract.md`
2. `docs/extractor-agent-plans/stream-restructure-orchestrator-core.md`

Focus:
1. strict-mode unrecovered section failures emit dedicated public error
2. warning payload v1 includes additive `section_failure_count`
3. keep backward compatibility for existing warning payload consumers

Completion:
1. strict modular residual failures now terminate with `extraction_failed:section_failures_remaining`
2. warning payload v1 carries `section_failure_count` additively
3. tasks/API/store/docs/tests updated and green

### Change Set 2: Effective Reasoning Canonicalization

Plan docs:
1. `docs/extractor-agent-plans/stream-provider-expansion.md`

Focus:
1. resolve `effective_reasoning` once per run path
2. pass/persist effective value consistently across task + CLI pipelines
3. keep provider fail-fast guarantees intact

Completion:
1. API enqueue, worker path, extraction pipeline, batch CLI, and eval CLI now pass/persist resolved `effective_reasoning`
2. added regression tests for worker/API/eval/batch defaults and propagation

### Change Set 3: Stage Status UX Closure

Plan docs:
1. `docs/extractor-agent-plans/stream-restructure-orchestrator-core.md`

Focus:
1. parse canonical `[stage:<name>]` status shape in extractor UI
2. present stable stage labels + concise detail for operators
3. preserve compatibility with legacy plain-text statuses

Completion:
1. extractor UI now parses canonical stage/status messages into label + detail
2. legacy plain-text status messages remain supported
3. Playwright tests added for canonical and legacy rendering

### Change Set 4: Coding Index Lifecycle + Concurrency Hardening

Plan docs:
1. `docs/extractor-agent-plans/stream-coding-bridge.md`

Focus:
1. wire coding index cleanup to worker lifecycle
2. add concurrency-focused tests for reusable index behavior
3. preserve non-fatal coding behavior contract

Completion:
1. worker shutdown hook now closes reusable coding indexes
2. coding bridge serializes shared-index access for connection safety
3. added concurrency + lifecycle reinit tests

## Coordination Rules

1. Change set 1 owns reliability warning/error semantics.
2. Change set 2 owns reasoning-resolution consistency across runtime paths.
3. Change set 3 owns extractor UI stage status parsing behavior.
4. Change set 4 owns coding index lifecycle and concurrency behavior.

## Validation Requirements

Per change set minimum:

1. Change set 1: `uv run pytest tests/test_tasks.py tests/test_api.py -q`
2. Change set 2: `uv run pytest tests/test_tasks.py tests/test_cli.py tests/test_config.py -q`
3. Change set 3: `uv run pytest tests/test_ui.py -q`
4. Change set 4: `uv run pytest tests/test_coding_bridge.py tests/test_tasks.py -q`

After each change set:

1. `task lint`
2. `task test`

## Kickoff Outputs (required)

1. Stream plan docs updated with concrete run state, risks, and remaining work.
2. Concise `docs/DEV_LOG.md` entry per stream with validation evidence.
3. Integration-ready branch tips for staged merge order.
