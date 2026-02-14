# Agent Restructuring Plan

Last updated: 2026-02-14
Status: Active (parallel execution)

## Why We Are Changing

The current extractor flow is too monolithic for latency, progress visibility, and focused retries. We are moving to a modular, provider-agnostic architecture where retries and diagnostics happen at small unit boundaries.

## Locked Decisions

1. Orchestration approach: PydanticAI workers + deterministic Python orchestration.
2. Work mode: parallel streams in separate worktrees.
3. Coding scope: coding is included in Phase 1 API/UI contract work.
4. Retry principle: retry failed units only, not whole reports by default.

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
10. `completed` / `failed`

## Parallel Execution Streams

### Stream A (this worktree)

- Plan: `docs/extractor-agent-plans/stream-restructure-orchestrator-core.md`
- Worktree: `/Users/talkasab/repos/imaging-problem-list`
- Branch: `feature/restructure-orchestrator-core`
- Focus: orchestrator skeleton + stage/status contract wiring.

### Stream B (`-agent`)

- Plan: `docs/extractor-agent-plans/stream-provider-failfast-hardening.md`
- Worktree: `/Users/talkasab/repos/imaging-problem-list-agent`
- Branch: `feature/provider-failfast-hardening`
- Focus: effective reasoning resolution + fail-fast provider validation.

### Stream C (`-provider`)

- Plan: `docs/extractor-agent-plans/stream-coding-runtime-hardening.md`
- Worktree: `/Users/talkasab/repos/imaging-problem-list-provider`
- Branch: `feature/coding-bridge-runtime-hardening`
- Focus: coding bridge index lifecycle reuse + region-aware location search.

### Stream D (`-ui`)

- Plan: `docs/extractor-agent-plans/stream-coding-api-ui-contract.md`
- Worktree: `/Users/talkasab/repos/imaging-problem-list-ui`
- Branch: `feature/coding-progress-ui-api-contract`
- Focus: coding exposure in store/API/UI and progress display alignment.

## Merge Order

1. Stream B
2. Stream C
3. Stream A
4. Stream D

Rationale: B sets fail-fast contract; C is low-conflict runtime hardening; A introduces shared stage contract; D consumes finalized contracts.

## Coordination Rules

1. Stream A owns stage/status vocabulary.
2. Stream B owns reasoning resolution and provider validation behavior.
3. Stream C owns `coding_bridge.py` internals.
4. Stream D owns API response exposure and UI rendering.
5. Rebase before merge when shared files overlap (`tasks.py`, `api_models.py`, `store.py`).

## Validation Requirements

Per stream minimum:

1. Stream A: `uv run pytest tests/test_tasks.py -q`
2. Stream B: `uv run pytest tests/test_extraction.py tests/test_config.py tests/test_cli.py tests/test_batch_cli.py tests/test_tasks.py -q`
3. Stream C: `uv run pytest tests/test_coding_bridge.py tests/test_tasks.py -q`
4. Stream D: `uv run pytest tests/test_store.py tests/test_api.py tests/test_ui.py -q`

Final integration on `dev`:

1. `task lint`
2. `task test`

## Follow-on (after integration)

1. Close Stage 3 eval evidence stream.
2. Reconcile reliability-contract stream with new stage/status contract.
3. Start modular section extraction + targeted repair rollout behind feature flag.
