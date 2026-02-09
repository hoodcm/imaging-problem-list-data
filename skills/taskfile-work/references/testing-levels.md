# Testing Levels for Task-Based Workflows

Use this convention unless project constraints require different naming.

## Task Names

1. `test:unit`
2. `test:integration`
3. `test:smoke`
4. `test` (aggregate)

## Expected Behavior

## `test:unit`

1. Fast and deterministic.
2. No Docker or external network dependencies.
3. Runs on every local edit cycle.

## `test:integration`

1. Cross-process or service boundary checks.
2. May use Docker services (databases, brokers, workers).
3. Optional in local default run if expensive.

## `test:smoke`

1. Highest-level health and contract verification.
2. Exercises "happy path + terminal failure semantics" where relevant.
3. Usually slower and environment-dependent.

## `test` Aggregate

Recommended behavior:

1. Always run `test:unit`.
2. Gate integration/smoke with vars (for example: `RUN_INTEGRATION=1`, `RUN_SMOKE=1`).
3. Fail fast on first failing level.

## Minimal Example

```yaml
version: "3.44"

tasks:
  test:
    desc: Run layered tests (unit always; integration/smoke optional)
    cmds:
      - task: test:unit
      - task: test:integration
        vars: { RUN: '{{default "0" .RUN_INTEGRATION}}' }
      - task: test:smoke
        vars: { RUN: '{{default "0" .RUN_SMOKE}}' }

  test:unit:
    desc: Run fast deterministic tests
    cmds:
      - uv run pytest tests -m "not integration"

  test:integration:
    desc: Run integration tests (set RUN=1)
    if: '{{eq .RUN "1"}}'
    cmds:
      - uv run pytest tests -m integration

  test:smoke:
    desc: Run smoke tests (set RUN=1)
    if: '{{eq .RUN "1"}}'
    cmds:
      - uv run python -m your_project.smoke
```
