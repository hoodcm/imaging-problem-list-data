# Validator Prompt Example (Current)

This file reflects the current chunk-level validator review contract in:

- `src/finding_extractor/extraction_review.py`
- `docs/extractor-agent-plans/validator-review-redesign-plan.md`

There is no max-rejections/max-retries cap in the validator response schema.

## System Prompt (Current)

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

Return one decision object for the provided report_chunk_id with fields:
- report_chunk_id
- should_reextract
- problems[] where each item has raw_extracted_finding_index, extract_problem_type, problem_detail
- rationale
If should_reextract is false, return problems as an empty list.
```

## User Prompt Template (Current)

```text
Review chunk-level finding representation quality.
For each structured data extraction, compare target chunk text and extracted findings.

EXTRACTION_TASK_SUMMARY
- Evaluate extraction quality for this report_chunk; do not perform a fresh extraction.
- Evidence boundary: only REPORT_CHUNK is evidence; surrounding context is advisory.
- Check that ALL clinically meaningful findings in REPORT_CHUNK are represented, and that EACH extracted finding is supported by REPORT_CHUNK.
- Presence labels must match text intent: present, absent, possible, indeterminate.
- Explicit negatives should be represented as clinically meaningful absent findings; blanket negatives should map to appropriately scoped absent findings (e.g., "clear lungs" -> {"finding_name": "pulmonary parenchymal abnormality", "presence": "absent"}), not unrelated or over-specific absent findings.
- Finding and location names should use STANDARD terminology (not raw report phrasing), and should not be more specific than the chunk supports.
- Location fields should be clinically plausible and text-supported (or clearly inferable).
- Verbatim evidence requirement applies: extracted evidence must be exact chunk text, not paraphrase.

REPORT_CHUNK_ID
{report_chunk_id}

EXAM_INFO
- exam_name: {exam_name}
- modality: {modality_or_unknown}
- body_part: {body_part_or_unknown}

SECTION
{section_name}

PRECEDING_CHUNK_CONTEXT
{preceding_chunk_context_or_(none)}

REPORT_CHUNK
{report_chunk}

FOLLOWING_CHUNK_CONTEXT
{following_chunk_context_or_(none)}

CHUNK_EXTRACTION
| raw_extracted_finding_index | finding_name | presence | body_region | specific_location |
|---|---|---|---|---|
| 0 | ... | ... | ... | ... |
```

## Expected Structured Response Shape (Current)

```json
{
  "report_chunk_id": "findings_1_chunk_2",
  "should_reextract": true,
  "problems": [
    {
      "raw_extracted_finding_index": 0,
      "extract_problem_type": "missed_finding",
      "problem_detail": "Chunk mentions mild bibasilar atelectasis not represented in extracted findings."
    }
  ],
  "rationale": "One clinically meaningful finding is missing."
}
```

Notes:

- One validator call reviews one chunk and returns one chunk decision.
- `problems` is empty when `should_reextract=false`.
- `extract_problem_type` values: `hallucination`, `missed_finding`, `wrong_presence`, `over_specific_finding_name`, `incorrect_blanket_negative`, `incorrect_location`, `other`.
