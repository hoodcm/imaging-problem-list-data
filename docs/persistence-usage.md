# Persistence Usage

This guide is for developers/agents who use the extraction persistence layer, not modify it.

## What It Gives You

- Report de-duplication (same report text is stored once).
- Versioned extraction runs (each run is a new extraction record).
- Provenance tracking (`model_name`, `reasoning_effort`, extraction timestamp).
- Human feedback capture (`add_finding`, `update_finding`, `comment`).
- Fully async persistence methods for FastAPI-style async apps.

## High-Level Schema Overview

The persistence layer stores three top-level entities:

1. `reports`
2. `extractions`
3. `corrections`

`reports` -> `extractions` is one-to-many.  
`extractions` -> `corrections` is one-to-many.

Extraction child content (findings, attributes, non-finding segments) is stored as JSON in:
- `extractions.extraction_json`

## Current Scope

Persistence is available through both:
- Python API (`ExtractionStore`)
- CLI (`finding-extractor --store`)

CLI persistence is optional and disabled by default.

## Python API (Store) Example

```python
from pathlib import Path

from finding_extractor.models import ExamInfo, ReportExtraction
from finding_extractor.store import ExtractionStore

store = ExtractionStore(Path(".finding_extractor.db"))
await store.init()

report = await store.upsert_report("Report text here", source_ref="example.md")
extraction = await store.create_extraction(
    report_id=report.id,
    extraction=ReportExtraction(exam_info=ExamInfo(study_description="Chest XR")),
    model_name="openai:gpt-5-mini",
)

await store.record_correction(
    extraction_id=extraction.id,
    correction_type="comment",
    comment="Recheck this extraction.",
    created_by="reviewer@example.org",
)
await store.close()
```

## Common Operations

- Store or reuse report: `upsert_report(...)`
- Store new extraction run: `create_extraction(...)`
- Add correction/comment: `record_correction(...)`
- Read corrections: `list_corrections(...)`

## CLI Examples

No persistence (default):

```bash
uv run finding-extractor sample_data/example2/xr_chest_20210614.md
```

With persistence:

```bash
uv run finding-extractor sample_data/example2/xr_chest_20210614.md \
  --store \
  --db-path .finding_extractor.db
```

With persistence + validation:

```bash
uv run finding-extractor sample_data/example2/xr_chest_20210614.md \
  --store \
  --validate
```

## Where To Look Next

- Internals schema and design: `docs/persistence-internals.md`
- CLI notes/future enhancements (archived): `docs/archive/persistence-cli-plan.md`
- Implementation: `src/finding_extractor/store.py`
