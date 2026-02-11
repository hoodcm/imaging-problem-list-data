---
name: taskfile-work
description: Design, implement, and maintain Taskfile-based developer workflows. Use when users ask to create or refactor Taskfiles, replace shell-wrapper scripts with Task tasks, define testing levels (unit/integration/smoke), add task conventions, or align automation with Task best practices from official Task docs.
---

# Taskfile Work

Use this skill to implement or improve `Taskfile.yml` automation with a lean, reliable approach.

## Core Rules

1. Keep Task as orchestration only.
2. Put deep logic in Python modules/scripts, not in long shell command blocks.
3. Use clear task names and `desc` so `task --list` is usable as the primary interface.
4. Prefer explicit `requires`, `preconditions`, and `if` guards over implicit assumptions.
5. Keep the task graph small and composable.

## Workflow

1. Read existing automation (`Taskfile.yml`, scripts, CI commands, docs).
2. Propose a minimal task graph:
   - setup/lint/test/unit/integration/smoke/run/stack
3. Move complex shell logic into Python (or existing project scripts) if needed.
4. Implement/refactor Task targets as wrappers around those commands.
5. Validate with:
   - `task --list`
   - `task --summary <task>`
   - `task --dry <task>`
6. Execute representative tasks and fix portability/quoting issues.

## Testing Levels Convention

Use these levels unless the user requests otherwise:

1. `test:unit`: fast, deterministic local tests (no containers/network).
2. `test:integration`: cross-process/service tests (optional, usually Docker-backed).
3. `test:smoke`: highest-level end-to-end health checks.

Provide one aggregate `test` task that runs levels in order, with optional integration/smoke controlled by vars.

## Implementation Pattern

For each task:

1. Add `desc`.
2. Add `sources`/`generates` only when caching is meaningful.
3. Add `requires` for mandatory vars (optionally enum-constrained).
4. Keep commands short; call Python entrypoints for non-trivial logic.

## References

Read these files as needed:

- `references/official-docs.md` for canonical Task docs and what each page is for.
- `references/best-practices.md` for recommended patterns and anti-patterns.
- `references/testing-levels.md` for standard task names and expected behavior.
