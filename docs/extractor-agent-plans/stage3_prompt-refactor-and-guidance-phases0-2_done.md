# Stage 3 (Phases 0-2) Done: Prompt Refactor and Schema Guidance

Completed: 2026-02-12

## What this completed slice does

This completed slice refactored prompt construction into modular blocks and improved guidance for deduplication, presence classification, and attribute extraction.

## Delivered

1. Prompt blocks moved into dedicated prompt module with test coverage.
2. Few-shot examples externalized to YAML.
3. Schema-driven prompt rules tightened for section priority and output consistency.

## Main artifacts

1. `src/finding_extractor/prompt.py`
2. `src/finding_extractor/examples/`
3. `tests/test_prompt.py`
4. `tests/test_models.py`
5. `tests/test_extraction.py`

## Note

Stage 3 Phase 3 (report-section detection/source tracking) is implemented but closed separately via Stream Eval Closure after eval-evidence signoff.
