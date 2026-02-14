# Stream B: Provider Fail-Fast Hardening

Last updated: 2026-02-14
Status: Active
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
   1. Validate `default_reasoning` when provided.
3. Update preflight callsites to validate effective reasoning:
   1. `src/finding_extractor/tasks.py`
   2. `src/finding_extractor/api_services.py`
   3. `src/finding_extractor/extraction_pipeline.py`
   4. `src/finding_extractor/eval_cli.py`
   5. `src/finding_extractor/batch_cli.py`
4. Add policy coverage for OpenRouter model IDs in `tests/test_model_policy.py`.

## Files expected to change

1. `src/finding_extractor/providers.py`
2. `src/finding_extractor/config.py`
3. `src/finding_extractor/tasks.py`
4. `src/finding_extractor/api_services.py`
5. `src/finding_extractor/extraction_pipeline.py`
6. `src/finding_extractor/eval_cli.py`
7. `src/finding_extractor/batch_cli.py`
8. `tests/test_extraction.py`
9. `tests/test_config.py`
10. `tests/test_tasks.py`
11. `tests/test_cli.py`
12. `tests/test_batch_cli.py`
13. `tests/test_model_policy.py`

## Test plan

1. `uv run pytest tests/test_extraction.py tests/test_config.py tests/test_cli.py tests/test_batch_cli.py tests/test_tasks.py tests/test_model_policy.py -q`

## Acceptance criteria

1. Invalid default reasoning fails before model invocation.
2. Ollama + incompatible reasoning default fails preflight.
3. No bad reasoning path produces runtime `KeyError`.
4. Stream test scope is green.
