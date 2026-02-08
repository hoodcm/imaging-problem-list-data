# Persistence Usage

This guide is for callers using `ExtractionStore`, not maintainers changing schema internals.

## What It Provides

- Report de-duplication by `text_hash`.
- Versioned extraction storage.
- Correction storage for reviewer feedback.
- Async job lifecycle storage for API polling.
- Async APIs suitable for FastAPI/TaskIQ contexts.

## Entities

Top-level tables:
1. `reports`
2. `extractions`
3. `corrections`
4. `jobs`

Relationships:
- `reports` -> `extractions` (one-to-many)
- `extractions` -> `corrections` (one-to-many)
- `reports` -> `jobs` (one-to-many)

## Typical Call Patterns

### Report + extraction write

```python
from pathlib import Path
from finding_extractor.models import ExamInfo, ReportExtraction
from finding_extractor.store import ExtractionStore

store = ExtractionStore(Path(".finding_extractor.db"))
await store.init()

report = await store.upsert_report("Report text", source_ref="example.txt")
extraction = await store.create_extraction(
    report_id=report.id,
    extraction=ReportExtraction(exam_info=ExamInfo(study_description="Chest XR")),
    model_name="openai:gpt-5-mini",
)

await store.close()
```

### Job lifecycle write/read

```python
await store.create_job(job_id="job-123", report_id=report.id, status="pending")
await store.mark_job_running("job-123")
await store.mark_job_completed("job-123", extraction_id=extraction.id)
job = await store.get_job("job-123")
```

### Correction write/read

```python
await store.record_correction(
    extraction_id=extraction.id,
    correction_type="comment",
    comment="Looks correct",
    created_by="reviewer@example.org",
)
corrections = await store.list_corrections(extraction.id)
```

## Read APIs

- `get_report(report_id)`
- `list_reports(limit=50, offset=0)`
- `get_extraction(extraction_id)`
- `list_extractions(report_id)`
- `get_job(job_id)`
- `list_corrections(extraction_id)`

## Write APIs

- `upsert_report(report_text, source_ref=None)`
- `create_extraction(...)`
- `record_correction(...)`
- `create_job(job_id, report_id, status="pending")`
- `mark_job_running(job_id)`
- `mark_job_completed(job_id, extraction_id)`
- `mark_job_failed(job_id, error)`

## Notes for API Consumers

`jobs.error` is intended for public API consumption and should contain stable, non-sensitive strings.
Do not rely on provider-specific raw exception text.

## Related Docs

- Internals: `docs/persistence-internals.md`
- API usage: `docs/api-usage.md`
- API internals: `docs/api-internals.md`
