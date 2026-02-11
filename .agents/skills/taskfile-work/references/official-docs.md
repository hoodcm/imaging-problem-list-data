# Official Task Docs (Primary Sources)

Use official docs first. Prefer these pages in this order:

1. Guide: https://taskfile.dev/docs/guide
2. Style Guide: https://taskfile.dev/docs/styleguide
3. Taskfile Versions: https://taskfile.dev/docs/taskfile-versions
4. Schema Reference: https://taskfile.dev/docs/reference/schema
5. CLI Reference: https://taskfile.dev/docs/reference/cli
6. Environment / Dotenv behavior: https://taskfile.dev/docs/reference/environment
7. Changelog: https://taskfile.dev/docs/changelog

## What to Pull From Each

1. `guide`: task syntax, includes, variables, execution model.
2. `styleguide`: naming, readability, maintainability.
3. `taskfile-versions`: feature gating and version pinning strategy.
4. `schema`: exact field behavior (`requires`, `preconditions`, `run`, `method`, etc.).
5. `cli`: operational flags (`--list`, `--summary`, `--dry`, `--status`).
6. `environment`: dotenv precedence and env resolution behavior.
7. `changelog`: verify recent behavior changes before recommending patterns.

## Reliability Note

Avoid relying on experimental features in production automation unless explicitly requested.
If used, document that choice and its risk.
