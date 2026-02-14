# Stream B: Provider Fail-Fast Hardening

Last updated: 2026-02-14
Status: Complete
Owner/worktree: `/Users/talkasab/repos/imaging-problem-list-agent` (`feature/provider-failfast-hardening`)

## Goal

Enforce fail-fast runtime validation for effective reasoning configuration across API, worker, and CLI entrypoints.

## In scope

1. Add canonical effective reasoning resolution.
2. Validate model/reasoning compatibility even when reasoning comes from defaults.
3. Fail early on invalid `IPL_REASONING`.
4. Remove runtime `KeyError`/late provider errors caused by bad reasoning levels.

## Out of scope

1. Orchestrator restructuring.
2. Coding bridge internals.
3. UI behavior changes.

## Implementation plan

1. In `src/finding_extractor/providers.py`:
   1. Add effective reasoning resolver (explicit -> env default -> provider default).
   2. Validate resolved level and provider compatibility centrally.
2. In `src/finding_extractor/config.py`:
   1. Type `default_reasoning` as `ReasoningLevel | None` (pydantic Literal validation).
3. Update preflight callsites to validate effective reasoning:
   1. `src/finding_extractor/tasks.py`
   2. `src/finding_extractor/api_services.py`
   3. `src/finding_extractor/extraction_pipeline.py`
   4. `src/finding_extractor/eval_cli.py`
   5. `src/finding_extractor/batch_cli.py`
4. Add policy coverage for OpenRouter model IDs in `tests/test_model_policy.py`.

## Architecture notes

- `resolve_effective_reasoning()` in `providers.py` is the **validation** boundary — called once at each preflight entrypoint.
- `get_model_settings()` in `providers.py` is a **pure builder** — it resolves the level using the same precedence but does not validate. Callers must validate first via `resolve_effective_reasoning()`.
- Config-level validation uses pydantic's `Literal` type on `default_reasoning` — invalid values are rejected at `Settings()` construction time.
- Callsites import `resolve_effective_reasoning` directly from `providers`, not through `agent.py`.

## Files changed

1. `src/finding_extractor/providers.py` — added `resolve_effective_reasoning()`
2. `src/finding_extractor/config.py` — typed `default_reasoning` as `ReasoningLevel | None`
3. `src/finding_extractor/tasks.py` — use `resolve_effective_reasoning()` instead of conditional validation
4. `src/finding_extractor/api_services.py` — same
5. `src/finding_extractor/extraction_pipeline.py` — same
6. `src/finding_extractor/eval_cli.py` — same
7. `src/finding_extractor/batch_cli.py` — same
8. `src/finding_extractor/agent.py` — removed unused re-export
9. `tests/test_extraction.py` — added `TestResolveEffectiveReasoning` class (8 tests)
10. `tests/test_config.py` — added default_reasoning validation tests (2 tests)
11. `tests/test_tasks.py` — added default reasoning incompatibility regression test
12. `tests/test_batch_cli.py` — added env default reasoning incompatibility test
13. `tests/test_model_policy.py` — added OpenRouter model ID validation tests (2 tests)

## Test plan

1. `uv run pytest tests/test_extraction.py tests/test_config.py tests/test_cli.py tests/test_batch_cli.py tests/test_tasks.py tests/test_model_policy.py -q`

## Acceptance criteria

1. Invalid default reasoning fails before model invocation. ✓
2. Ollama + incompatible reasoning default fails preflight. ✓
3. No bad reasoning path produces runtime `KeyError`. ✓
4. Stream test scope is green (130 tests). ✓

## Progress

### 2026-02-14: Effective Reasoning Resolution + Fail-Fast Validation ✓

**Core change:** Added `resolve_effective_reasoning()` to `providers.py` — canonical function that resolves the 3-tier reasoning precedence (explicit → env default → provider default) and validates the resolved level against provider compatibility in one step.

**Config hardening:** Typed `default_reasoning` field as `ReasoningLevel | None` in `config.py`, leveraging pydantic's built-in Literal validation so invalid `IPL_REASONING` values (e.g., `turbo`) are rejected at config load time.

**Layer separation:** `resolve_effective_reasoning()` handles validation at preflight boundaries. `get_model_settings()` remains a pure builder — it resolves the level with the same precedence chain but trusts that preflight already validated. This avoids redundant triple-validation through the call stack.

**Callsite updates:** All 5 preflight entrypoints now call `resolve_effective_reasoning()` unconditionally (imported directly from `providers`), closing the gap where `IPL_REASONING=high` + `IPL_MODEL=ollama:llama4` would pass preflight but crash at runtime.

**Test coverage:** 14 new regression tests covering:
- `resolve_effective_reasoning()` precedence and validation (8 tests)
- Config-level `IPL_REASONING` validation (2 tests)
- Task-level default reasoning incompatibility (1 test)
- Batch CLI default reasoning incompatibility (1 test)
- OpenRouter model ID validation (2 tests)

**Validation:** 130 tests passing, lint clean.
