# Taskfile Best Practices

These are practical defaults for maintainable Task usage.

## 1) Keep Taskfiles Thin

1. Use Task to orchestrate commands.
2. Move deep logic to Python scripts/modules.
3. Keep per-task command blocks short and readable.

## 2) Pin Version Intentionally

1. Set `version` to the minimum feature version required.
2. Do not assume all environments have the newest Task release.

## 3) Make Task Contracts Explicit

1. Use `requires` for mandatory inputs.
2. Use `preconditions` for fail-fast checks.
3. Use `if` for conditional skip behavior.

## 4) Design for Repeatability

1. Use `sources`/`generates` only where caching matters.
2. Use `run` policy intentionally (`always`, `once`, `when_changed`).
3. Avoid hidden state assumptions.

## 5) Keep Graphs Small

1. Build composable tasks (`lint`, `test:unit`, `test:integration`, `test:smoke`).
2. Add one aggregate task (`test`) that composes levels.
3. Avoid deep dependency chains unless needed.

## 6) Document Through Task Metadata

1. Add `desc` for every user-facing task.
2. Keep `summary` and task names precise.
3. Make `task --list` the primary discoverability surface.

## 7) Handle Environments Deliberately

1. Define dotenv/env precedence intentionally.
2. Do not silently depend on local shell state.
3. Require explicit env vars for sensitive credentials and external services.

## 8) Prefer Stable Features

1. Avoid experimental features for baseline automation.
2. If adopted, annotate why and what fallback exists.

## 9) Anti-Patterns

1. Monolithic shell blocks in Taskfile.
2. Duplicate logic across many tasks.
3. Hidden environment coupling.
4. Overly broad "do-everything" tasks without clear boundaries.
