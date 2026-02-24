# Validator Review Redesign Plan

Last updated: 2026-02-24  
Status: Proposed

## Purpose

Define the validator redesign as a dedicated, decision-complete plan separate from orchestrator core work.

## Scope

1. Chunk-scoped validator review contract.
2. Canonical naming for validator payloads/responses.
3. Structured feedback flow into chunk re-extraction.
4. Prompt language canon and migration constraints.

## Core Decisions

1. Validator is a chunk-level reviewer.
2. One validator invocation handles one `report_chunk`.
3. One validator response is one `extraction_review_decision` for one `report_chunk_id`.
4. Multi-chunk orchestration happens outside validator prompt/response contracts.
5. Re-extraction uses full replacement `chunk_extraction`, not delta patches.
6. Remove `validator_max_reextract_units` configuration entirely.
7. Hard cutover to the new single-chunk validator schema (no compatibility adapter for old report-level schema).
8. Keep stage vocabulary unchanged (`validator_review`) and adopt per-chunk status detail events plus final summary detail.

## Canonical Names

1. `report_chunk`
2. `report_chunk_id`
3. `preceding_chunk_context`
4. `following_chunk_context`
5. `exam_info`
6. `chunk_extraction`
7. `raw_extracted_finding`
8. `extract_problem_type`
9. `extraction_review_decision`

Deprecated in validator flow:

1. `unit`
2. `unit_label`
3. `unit card`
4. report-level `requests` response object

## Canonical Prompt Language (Verbatim, Normative)

The following system prompt text is normative and should be carried forward verbatim
except where explicit term migrations in this doc apply.

```text
You are a diligent radiology informatics assistant who carefully reviews the results of
extracting data structures representing imaging findings from chunks of unstructured radiology
report text.

Your goal is to determine whether the data structures provide an accurate representation of
natural language in the radiology report or if the extraction should be re-run with clarifying
instructions.

Issue patterns that justify re-extraction:
- extraction structure contains clinically meaningful content unsupported by the chunk text (hallucination)
- some report text describing a finding is not represented by any extraction data structure (missed finding)
- a structure describes a finding as being present when it is not, or absent when it is possible (wrong presence)
- finding name is more specific than described in the chunk text (too specific finding name)
- incorrect representation of a blanket negative (incorrect blanket negative)
- wrong or too-specific or general location information (incorrect location)

Do not request re-extraction for formatting/style differences alone.
```

Additional normative instruction intent:

```text
Review chunk-level finding representation quality.
For each structured data extraction, compare target chunk text and extracted findings.
Use the EXTRACTION_TASK_SUMMARY as binding context for what the extractor was instructed to do.
Judge extraction quality against that task summary before recommending re-extraction.
Do not ignore the EXTRACTION_TASK_SUMMARY.
```

Canonical user-payload framing MUST include this section header and content block:

```text
EXTRACTION_TASK_SUMMARY
- Evaluate extraction quality for this report_chunk; do not perform a fresh extraction.
- Evidence boundary: only REPORT_CHUNK is evidence; surrounding context is advisory.
- Check that ALL clinically meaningful findings in REPORT_CHUNK are represented, and that EACH extracted finding is supported by REPORT_CHUNK.
- Presence labels must match text intent: present, absent, possible, indeterminate.
- Explicit negatives should be represented as clinically meaningful absent findings; blanket negatives should map to appropriately scoped absent findings (e.g., "clear lungs" -> {"finding_name": "pulmonary parenchymal abnormality", "presence": "absent"}), not unrelated or over-specific absent findings.
- Finding and location names should use STANDARD terminology (not raw report phrasing), and should not be more specific than the chunk supports.
- Location fields should be clinically plausible and text-supported (or clearly inferable).
- Verbatim evidence requirement applies: extracted evidence must be exact chunk text, not paraphrase.
```

## Prompt Language Migration Map (Terms Only)

When implementing redesigned payloads, preserve language intent and only apply these
required term migrations:

1. `unit` -> `report_chunk`
2. `unit_label` -> `report_chunk_id`
3. `target_text` -> `report_chunk`
4. `prev_context_text` -> `preceding_chunk_context`
5. `next_context_text` -> `following_chunk_context`
6. `extracted_findings` rows -> `raw_extracted_findings` rows under `chunk_extraction`

No further voice/style rewrites without explicit review.

## Validator Input Payload Contract (Single Chunk)

Each validator call payload includes exactly one chunk:

1. `REPORT_CHUNK_ID`
2. `EXAM_INFO`
3. `PRECEDING_CHUNK_CONTEXT`
4. `REPORT_CHUNK`
5. `FOLLOWING_CHUNK_CONTEXT`
6. `CHUNK_EXTRACTION` with `raw_extracted_findings[]` rows:
   - finding_name
   - presence
   - body_region
   - specific_location
7. `EXTRACTION_TASK_SUMMARY` (required)

Single-chunk strictness:

1. Payload MUST describe exactly one `report_chunk_id`.
2. Payload MUST NOT contain aggregate multi-chunk sections.
3. Validator interface MUST be one chunk input -> one `extraction_review_decision`.

`EXTRACTION_TASK_SUMMARY` must summarize extractor intent: presence labels, verbatim expectations,
specificity expectations, location handling, and negative/blanket-negative handling.

## Validator Output Schema (Single Chunk)

`extraction_review_decision`:

1. `report_chunk_id: str`
2. `should_reextract: bool`
3. `problems: list[problem]`
4. `rationale: str | null`

`problem`:

1. `raw_extracted_finding_index: int | null`
2. `extract_problem_type: enum`
3. `problem_detail: str` (required, short, actionable)

`extract_problem_type` baseline:

1. `hallucination`
2. `missed_finding`
3. `wrong_presence`
4. `over_specific_finding_name`
5. `incorrect_blanket_negative`
6. `incorrect_location`
7. `other` (requires meaningful `problem_detail`)

## Feedback Loop into Re-extraction

Re-extraction prompt must include:

1. `EXAM_INFO`
2. `PRECEDING_CHUNK_CONTEXT`
3. `REPORT_CHUNK`
4. `FOLLOWING_CHUNK_CONTEXT`
5. `PREVIOUS_CHUNK_EXTRACTION` (indexed `raw_extracted_findings`)
6. `RE-EXTRACTION_FEEDBACK` (indexed problems with `extract_problem_type` + `problem_detail`)

Output mode for retries:

1. Full replacement `chunk_extraction`
2. No delta patch contract

## Rejected Alternatives

1. Report-level/multi-chunk validator response schema as primary interface.
2. “unit cards” naming.
3. Feedback-free retries.
4. Full conversation replay as retry context.
5. Delta patch retry output.

## Relevant Carryover from Current Uncommitted Work

Potentially reusable ideas after code revert:

1. Dedicated model selection for validator-triggered re-extraction.
2. Dedicated reasoning selection for validator-triggered re-extraction.
3. Runtime config keys for validator re-extract model/reasoning.
4. Orchestrator resilience improvement to drain/cancel exam-info task exceptions on early failure.

## Runtime Status Contract (Validator Stage)

Stage name remains `validator_review`. Emit detail lines in this form:

1. `chunk_review_start report_chunk_id=...`
2. `chunk_review_decision report_chunk_id=... should_reextract=... problem_count=...`
3. `chunk_reextract_start report_chunk_id=...`
4. `chunk_reextract_complete report_chunk_id=...`
5. final summary detail: `reviewed_chunks=... reextract_chunks=...`

Notes:

1. This is a status/logging contract update only (no API contract change).
2. Existing machine-parseable stage prefix contract remains unchanged.

## Source Prompt Artifact

`prompts/validator_prompt_example.md` remains the editable working artifact for prompt
text/examples and should be kept aligned with this plan.
