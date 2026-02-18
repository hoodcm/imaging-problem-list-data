# Chunk Extraction Prompt + Schema Plan

Last updated: 2026-02-18  
Status: in_progress (Slice B runtime integration)

## Goal

Use a dedicated chunk extraction prompt/schema for chunk sub-agent calls so
chunk extraction is smaller, clearer, and more reliable than full-report prompt
reuse.

## Why

Current behavior still carries full-report prompt assumptions into chunk work.
That mismatch inflates prompt size and increases latency/retry risk for chunk
calls.

## Locked Decisions

1. Chunk extraction uses dedicated schema (`ChunkFinding`, `ChunkExtraction`,
   `ChunkExtractionResult`) focused on finding extraction only.
2. Attributes stay loose key/value (not closed enum).
3. Chunk prompt examples must come from one source of truth:
   `src/finding_extractor/examples/chunk_examples.yaml`.
4. No hardcoded ad hoc examples in prompt code.
5. Chunk prompt excludes full-report dedupe/output-contract instructions.
6. Final assembled output contract remains `ReportExtraction`.
7. Prompt builder may select a deterministic subset of YAML examples to stay
   within prompt budget.

## New Context Incorporated (2026-02-18)

1. Prompt examples must show complete location fields in extracted pieces:
   `body_region`, `specific_anatomy`, `laterality`.
2. Remove unnecessary explicit phrasing like "Return a ChunkExtraction response"
   from chunk prompt instructions.
3. Example drift bug was identified: hardcoded "Example C" in prompt code did
   not exist in YAML and violated source-of-truth expectations.
4. Action taken: move chunk examples to YAML-backed rendering path only.

## Scope

### Slice A (active)

1. Add chunk schema models with concise field descriptions.
2. Build chunk prompt from rules + YAML-backed chunk examples.
3. Keep runtime wiring unchanged in this slice.
4. Add/adjust unit tests to enforce prompt content expectations.

### Slice B (active)

1. Wire chunk sub-agent execution to dedicated chunk prompt/schema.
2. Adapt chunk output to assembled `ReportExtraction` contract.
3. Keep exam-info handling deterministic pending Phase 2 metadata pass.

### Slice C

1. Expand orchestrator/runtime integration tests.
2. Add dynamic chunk-example selection policy.
3. Update docs for final extractor architecture and usage.

## Acceptance Criteria (Slice A)

1. `build_chunk_system_prompt()` loads examples from YAML (no hardcoded examples).
2. Prompt includes fleshed location outputs in example "expected extracted
   pieces".
3. Prompt excludes full-report dedupe/output-contract blocks.
4. Chunk prompt remains materially smaller than full-report prompt.
5. Lint/type/tests are green.
6. One real isolated chunk extraction via `agent.run()` succeeds.

## Validation Plan

1. `task lint` + `task test` for lint/format/type/test workflow.
2. Focused chunk prompt tests in `tests/test_chunk_prompt.py`.
3. One live isolated chunk extraction smoke run using a chunk from
   `sample_data/example2`.
