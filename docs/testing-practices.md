# Testing Practices

Project-specific pytest conventions for this repository.

For generic pytest best practices, use `.agents/skills/pytest-testing-patterns/`.

## Scope

- This document is the source of truth for testing patterns that are specific to this codebase.
- `docs/testing_plan.md` tracks sequencing and rollout status.
- Test behavior truth still lives in `tests/` and runtime code.

## Primary Commands

Use `Taskfile.yml` as the workflow surface:

```bash
task lint
task test
task test:smoke
```

For targeted local iteration:

```bash
uv run pytest tests/test_api.py -q
```

## Test Topology

- Core backend behavior:
  - `tests/test_store.py`
  - `tests/test_api.py`
  - `tests/test_tasks.py`
- CLI and batch/eval command behavior:
  - `tests/test_cli.py`
  - `tests/test_batch_cli.py`
  - `tests/test_eval_cli.py`
- Config/policy/catalog contracts:
  - `tests/test_config.py`
  - `tests/test_model_policy.py`
  - `tests/test_model_catalog.py`
- UI and integration:
  - `tests/test_ui.py`
  - `tests/test_integration.py`

## Shared Fixture Catalog (`tests/conftest.py`)

### `_clear_cached_settings` (autouse, function scope)

- Purpose: prevent settings cache leakage across tests that mutate env vars.
- Usage: automatic; no direct fixture argument needed.

### `context_capture_logger` (function scope)

- Returns: `ContextCaptureLogger`
- Purpose: capture structlog event kwargs plus active contextvars in logging tests.
- Primary use: request/task context binding tests.

### `cli_runner` (function scope)

- Returns: `click.testing.CliRunner`
- Purpose: shared CLI runner for CLI/batch/eval test modules.

### `store_factory` (function scope)

- Returns: async context-manager factory that yields initialized `ExtractionStore`.
- Purpose: consistent async store setup/teardown across store/API/task tests.

### `runtime_logging_spy` (function scope)

- Returns: `RuntimeLoggingSpy`
- Purpose: patch and capture startup `configure_logfire(...)` and `setup_logging(...)` calls.
- Primary use: API/CLI/batch/eval/worker runtime logging bootstrap tests.

## Pattern Rules For This Repo

1. Promote fixtures to `tests/conftest.py` only when reused by 2+ modules or clearly global.
2. Keep API-specific app/client fixtures local to API tests unless reuse becomes real.
3. Keep assertions explicit at callsites for startup/logging wiring tests.
4. Use per-test DB paths or explicit wrappers when store tests need filename clarity.
5. Keep log assertions PHI-safe and metadata-focused.

## Anti-Patterns (Repository-Specific)

1. Importing helper fixtures from `tests.<module>` paths instead of pytest fixture discovery.
2. Creating new global fixtures for one-off local test setup.
3. Adding hidden side effects to autouse fixtures.
4. Reintroducing direct duplicate setup already covered by `cli_runner`, `store_factory`, or `runtime_logging_spy`.

## Update Policy

1. Any new shared fixture in `tests/conftest.py` must be documented here.
2. Any removed/renamed shared fixture must be updated here in the same change.
3. If guidance is generic pytest advice, move it to `.agents/skills/pytest-testing-patterns/` and keep this file focused on repo specifics.

## Related Docs

- Plan and slice status: `docs/testing_plan.md`
- Dev history: `docs/DEV_LOG.md`
- Agent onboarding: `AGENTS.md`
- Contributor architecture map: `CLAUDE.md`
