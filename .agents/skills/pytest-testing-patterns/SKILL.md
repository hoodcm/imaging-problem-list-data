---
name: pytest-testing-patterns
description: Research and apply general best practices for testing Python modules with pytest. Use when designing test strategy, writing/cleaning pytest fixtures, selecting mocking/parametrization patterns, or reviewing test quality for clarity and maintainability.
---

# Pytest Testing Patterns

Use this skill for reusable pytest guidance that is not specific to this repository.

## Scope Boundary

- Generic guidance belongs here (fixture design, mocking, parametrization, async testing, test reliability).
- Repository-specific conventions belong in `docs/testing-practices.md`.
- If guidance conflicts, follow project docs for this repo.

## Workflow

1. Confirm the target test type:
   - pure unit
   - async/service integration
   - CLI
   - API
2. Apply the smallest pytest-native pattern that solves the problem.
3. Prefer readability over fixture abstraction when reuse is low.
4. Keep assertions behavior-focused; avoid coupling tests to implementation details.
5. Add or update tests only where behavior changes.

## Decision Rules

1. Fixture scope:
   - default to function scope
   - broaden scope only for expensive setup with clear safety
2. Mocking:
   - mock external boundaries (network, filesystem, time, third-party services)
   - do not mock core behavior under test unless unavoidable
3. Parametrization:
   - use `@pytest.mark.parametrize` for repeated shape assertions
   - keep each case small and named when intent is not obvious
4. Async tests:
   - use `pytest.mark.asyncio` (or repo-standard async plugin pattern)
   - keep event loop lifetime predictable and isolated
5. Failure clarity:
   - each test should fail with a single, obvious reason

## Anti-Patterns

- Overusing autouse fixtures with hidden side effects
- Deep fixture dependency chains that hide test setup
- Re-implementing pytest features via custom helper frameworks
- Massive "kitchen sink" tests validating too many concerns

## References

Read as needed:

- `references/official-pytest-guidance.md`
- `references/practical-patterns.md`
