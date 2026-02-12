# Official Pytest Guidance

Primary references:

1. https://docs.pytest.org/en/stable/
2. https://docs.pytest.org/en/stable/explanation/goodpractices.html
3. https://docs.pytest.org/en/stable/how-to/fixtures.html
4. https://docs.pytest.org/en/stable/how-to/parametrize.html
5. https://docs.pytest.org/en/stable/how-to/monkeypatch.html
6. https://docs.pytest.org/en/stable/explanation/flaky.html

## High-Signal Principles

1. Prefer plain `assert` with introspection over custom assertion wrappers.
2. Keep tests independent and order-agnostic.
3. Use fixtures for setup sharing, not to hide core test intent.
4. Use parametrization instead of copy-pasted test bodies.
5. Keep plugins minimal and justified.
6. Make flaky behavior explicit and fix root causes instead of tolerating random failures.

## Fixture Heuristics

1. Function scope by default.
2. Broader scope (`module`/`session`) only when setup is expensive and state is safely isolated.
3. Use `yield` fixtures for teardown that must always run.
4. Keep fixture names descriptive and domain-oriented.

## Mocking Heuristics

1. Mock I/O boundaries; avoid mocking local pure logic.
2. Prefer `monkeypatch` or targeted patching over broad global patching.
3. Assert outcomes and side effects that matter to behavior, not call counts alone.

## Collection/Layout Heuristics

1. Keep tests in `tests/`.
2. Use `test_*.py` naming consistently.
3. Keep module-local fixtures local unless reused across modules.
