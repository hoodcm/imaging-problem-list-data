# Exam Info Sub-Agent Improvement Plan

## Problem

The exam info sub-agent returns vague results like "Radiological Study" because it has a minimal prompt with no examples, uses free-form fields, doesn't leverage the filename, and uses an overly complex report context strategy.

## Changes

1. **Constrained output types**: Add `Modality`, `BodyRegion`, `Contrast` Literal type aliases in `models.py`. Constrain `ExamInfo.modality` to `Modality`, add `body_region: BodyRegion | None` and `contrast: Contrast | None` fields.

2. **Rewritten prompt**: Directive prompt with priority-of-evidence, constrained vocabularies, body_part vs body_region distinction, contrast guidance, study_description format examples, and anti-patterns.

3. **Simplified report context**: Replace complex header extraction (`_build_exam_info_report_headers`) with first-20-lines of report text.

4. **Few-shot examples**: Embedded examples for CT, XR, MR, US covering multi-region, contrast, laterality, and body_region mapping.

5. **New DB columns**: `body_region` and `contrast` nullable text columns on `extractions` table.

## Files Modified

- `src/finding_extractor/models.py` — Type aliases, ExamInfo fields
- `src/finding_extractor/extractor/exam_info_agent.py` — Model, prompt, context, conversion
- `src/finding_extractor/extractor/orchestrator.py` — Remove `_build_exam_info_report_headers`, update call site
- `src/finding_extractor/extractor/runtime.py` — Remove `report_headers` from default fn
- `src/finding_extractor/cli.py` — Display new fields
- `src/finding_extractor/extractor/review.py` — Add fields to EXAM_INFO block
- `src/finding_extractor/store.py` — Add columns to extraction record
- `src/finding_extractor/eval/datasets.py` — Fix body_region to use `.body_region`
- `tests/test_exam_info_agent.py` — Update tests
- `alembic/` — Migration for new columns
