# Practical Patterns

## Pattern: Small AAA Tests

- Arrange: minimal setup and test data
- Act: one behavior invocation
- Assert: specific expected outcome

Use this pattern when a test can stay focused on one contract.

## Pattern: Parametrize for Matrix Inputs

Use `pytest.mark.parametrize` when:

- only inputs/expected outputs vary
- setup remains the same
- repeated tests are otherwise copy-paste

Avoid parametrizing huge objects where dedicated named tests are clearer.

## Pattern: Explicit Boundary Mocks

Mock only external dependencies:

- network clients
- filesystem access
- wall clock and UUID randomness
- process environment where needed

Keep business rules real to preserve test value.

## Pattern: Async Service Tests

For async components:

1. isolate test DB/temp paths per test
2. use async fixtures/context managers for setup and teardown
3. avoid cross-test mutable globals
4. assert terminal states and observable side effects

## Pattern: CLI Tests

1. use a shared `CliRunner` fixture
2. isolate filesystem writes (`isolated_filesystem()`)
3. assert exit code and user-facing output
4. avoid asserting internal command wiring unless behavior depends on it

## Pattern: API Tests

1. use test client lifecycles that exercise startup/shutdown
2. isolate persistence dependencies for determinism
3. assert API contract fields and status codes first
4. keep transport/runtime setup explicit in fixtures

## Review Checklist

1. Is the test name behavior-oriented?
2. Can the failure message quickly explain what regressed?
3. Is any fixture over-abstracted for single-module use?
4. Is there avoidable duplication that pytest already solves?
