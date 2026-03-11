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
1. `reports` — deduplicated report text with optional patient identifier
2. `extractions` — extraction runs with model output and usage stats
3. `corrections` — user feedback on extractions with author attribution
4. `jobs` — async extraction job lifecycle tracking
5. `users` — user accounts for correction attribution

Relationships:
- `reports` -> `extractions` (one-to-many)
- `extractions` -> `corrections` (one-to-many)
- `reports` -> `jobs` (one-to-many)
- `users` -> `corrections` (one-to-many via username FK)

## Typical Call Patterns

### Report + extraction write

```python
from pathlib import Path
from finding_extractor.models import ExamInfo, ExtractedReportFindings, ExtractionUsage
from finding_extractor.db.store import ExtractionStore

store = ExtractionStore(Path(".finding_extractor.db"))
error = await store.check_migration_current()
if error:
    await store.close()
    raise RuntimeError(error)
await store.init()

# Create report with optional patient_id
report = await store.upsert_report(
    "Report text",
    source_ref="example.txt",
    patient_id="MRN12345",  # optional
)

extraction = await store.create_extraction(
    report_id=report.id,
    extraction=ExtractedReportFindings(exam_info=ExamInfo(study_description="Chest XR")),
    model_name="openai:gpt-5-mini",
    usage=ExtractionUsage(
        requests=1,
        input_tokens=500,
        output_tokens=200,
        duration_ms=1234,
    ),
)
# extraction.usage is populated when reading back

await store.close()
```

The `usage` parameter is optional. When omitted (or `None`), usage columns are stored as `NULL`. When reading extractions via `get_extraction()` or `list_extractions()`, the `usage` field on `StoredExtraction` / `StoredExtractionDetail` is `None` if no usage data was recorded.

The `patient_id` parameter is optional. If provided on subsequent upserts of the same report text (deduplicated by hash), the patient_id will be updated if not already set.

### Job lifecycle write/read

```python
await store.create_job(job_id="job-123", report_id=report.id, status="pending")
await store.mark_job_running("job-123")
await store.mark_job_completed("job-123", extraction_id=extraction.id)
job = await store.get_job("job-123")
```

### Correction write/read

```python
# Create a user first (if not already exists)
user = await store.create_user(
    username="reviewer",
    name="Jane Reviewer",
    email="jane@example.org",
)

# Record correction with user attribution
await store.record_correction(
    extraction_id=extraction.id,
    correction_type="comment",
    comment="Looks correct",
    username="reviewer",  # FK to users table
    created_by="reviewer@example.org",  # optional legacy field
)
corrections = await store.list_corrections(extraction.id)
# corrections[0].username == "reviewer"
# corrections[0].created_by == "reviewer@example.org"
```

### User management

```python
# Create or update user (upsert semantics)
user = await store.create_user(
    username="jsmith",
    name="John Smith",
    email="john@example.com",
)

# Get user by username
user = await store.get_user("jsmith")  # returns StoredUser or None

# List all users (alphabetically ordered)
users = await store.list_users()
```

## Read APIs

- `get_report(report_id)` — returns `StoredReportDetail` with `patient_id`
- `list_reports(limit=50, offset=0)` — returns list of `StoredReport` with `patient_id`
- `get_extraction(extraction_id)`
- `list_extractions(report_id)`
- `get_job(job_id)`
- `list_corrections(extraction_id)` — returns `StoredCorrection` with `username` and `created_by`
- `get_user(username)` — returns `StoredUser` or `None`
- `list_users()` — returns list of `StoredUser` ordered by username

## Write APIs

- `upsert_report(report_text, source_ref=None, patient_id=None)` — patient_id optional
- `create_extraction(...)`
- `record_correction(..., username=None, created_by=None)` — username is FK to users table
- `create_job(job_id, report_id, status="pending")`
- `mark_job_running(job_id)`
- `mark_job_completed(job_id, extraction_id)`
- `mark_job_failed(job_id, error)`
- `create_user(username, name, email)` — upsert semantics

## Notes for API Consumers

`jobs.error` is intended for public API consumption and should contain stable, non-sensitive strings.
Do not rely on provider-specific raw exception text.

## Related Docs

- Internals: `docs/persistence-internals.md`
- API usage: `docs/api-usage.md`
- API internals: `docs/api-internals.md`
