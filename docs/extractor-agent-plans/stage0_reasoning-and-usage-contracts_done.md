# Stage 0 Done: Reasoning and Usage Contracts Hardening

Completed: 2026-02-11

## What Stage 0 does

Stage 0 established correctness contracts for reasoning settings and extraction usage accounting.

## Delivered

1. Reasoning-level validation and provider compatibility checks.
2. Explicit provider behavior for `reasoning="none"`.
3. Usage/duration capture and persistence in extraction metadata.
4. API/CLI/worker fail-fast behavior for invalid model+reasoning combinations.

## Main artifacts

1. `src/finding_extractor/agent.py`
2. `src/finding_extractor/models.py`
3. `alembic/versions/7537480089ba_add_usage_columns.py`
4. Tests in `tests/test_extraction.py`, `tests/test_api.py`, `tests/test_cli.py`
