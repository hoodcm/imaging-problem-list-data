# Data Model Consolidation Plan

## Problem Statement

The codebase has **three parallel type systems** for the same data, requiring manual
field-by-field conversion at every boundary:

```
SQLModel table rows  -->  frozen dataclasses  -->  Pydantic response models
   (store.py)              (store.py)              (api.py)
```

This results in ~150 lines of pure mapping boilerplate and multiple places where field lists
must be kept in sync manually. There are also several cross-cutting issues:

1. **Repeated `model_config = ConfigDict(extra="forbid")`** on every Pydantic model (~15
   times) instead of using a shared base class.
2. **Literal type definitions duplicated** in `store.py` and `api.py` for `JobStatus`,
   `CorrectionType`, `CorrectionStatus`.
3. **`# type: ignore[arg-type]`** annotations in store.py where SQLModel `str` columns are
   passed to dataclass fields typed as `Literal[...]`.
4. **Validation logic for corrections** lives in the store method rather than in the model.

## Goals

- Eliminate the intermediate frozen-dataclass layer.
- Establish a `StrictBaseModel` base class to DRY up model config.
- Centralize shared type definitions (status enums, correction types).
- Use Pydantic's `model_validate()` to replace manual field mapping.
- Reduce total boilerplate by ~150 lines without changing external API behavior.
- Keep all existing tests passing (adapting imports as needed).

## Non-Goals

- Changing the database schema or SQLModel table definitions.
- Changing the API response JSON shapes.
- Switching to sync SQLModel (we are keeping async).
- Removing TaskIQ or asyncer.

---

## Design: `StrictBaseModel`

### What is it?

A project-wide Pydantic base class that carries shared `model_config`:

```python
from pydantic import BaseModel, ConfigDict

class StrictBaseModel(BaseModel):
    """Project-wide base model: rejects unknown fields, clean serialization."""
    model_config = ConfigDict(extra="forbid")
```

### Why is this best practice?

This is a well-documented Pydantic v2 pattern:

- **`model_config` is inherited and merged** by child classes. A child can override individual
  settings while inheriting the rest. ([Pydantic docs: Model
  Config](https://docs.pydantic.dev/latest/concepts/config/))
- **Eliminates copy-paste** -- instead of repeating `model_config = ConfigDict(extra="forbid")`
  on 15 classes, define it once.
- **Consistency guarantee** -- every domain model automatically gets `extra="forbid"`. A new
  model that forgets to set this will still be strict because it inherits from the base.
- **Config propagates only through inheritance, not through field types.** This means each
  nested model class must also inherit from `StrictBaseModel` to get the strict behavior, which
  is exactly what we want -- explicit opt-in at the class level.

Example of child override (if ever needed):

```python
class FlexibleModel(StrictBaseModel):
    """This specific model allows extra fields."""
    model_config = ConfigDict(extra="ignore")  # overrides parent
```

### Where it lives

New file: `src/finding_extractor/base.py`

```python
"""Shared base classes for Pydantic models throughout the project."""

from pydantic import BaseModel, ConfigDict


class StrictBaseModel(BaseModel):
    """Base model for all domain and API models.

    Rejects unknown fields (extra="forbid") to catch schema drift and
    prevent LLM hallucination of unexpected output fields.
    """
    model_config = ConfigDict(extra="forbid")
```

Every existing model in `models.py` and `api.py` changes from:

```python
class ExamInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ...
```

to:

```python
from finding_extractor.base import StrictBaseModel

class ExamInfo(StrictBaseModel):
    ...
```

The `model_config` line is removed from each class -- it is inherited.

---

## Design: Centralized Type Definitions

### Current problem

`CorrectionType`, `CorrectionStatus`, and `JobStatus` are defined as `Literal` types in
`store.py:22-24` and `JobStatus` is re-defined in `api.py:25`. These same string values also
appear in SQLModel `CheckConstraint` definitions. Adding a new status means updating 3+ files.

### Solution

Move all shared Literal type aliases to `models.py` (or `base.py` -- but `models.py` is the
natural home since these are domain concepts):

```python
# models.py (new section near the top)

CorrectionType = Literal["add_finding", "update_finding", "comment"]
CorrectionStatus = Literal["pending", "accepted", "rejected", "applied"]
JobStatus = Literal["pending", "running", "completed", "failed"]
Presence = Literal["present", "absent", "indeterminate", "possible"]
```

Then `store.py` and `api.py` import from `models.py`:

```python
from finding_extractor.models import CorrectionType, CorrectionStatus, JobStatus
```

The `CheckConstraint` strings in `store.py` should reference these programmatically to stay in
sync:

```python
from typing import get_args

def _literal_check(column: str, literal_type) -> str:
    """Build a SQL CHECK constraint from a Literal type."""
    values = ", ".join(f"'{v}'" for v in get_args(literal_type))
    return f"{column} IN ({values})"

class CorrectionRow(SQLModel, table=True):
    __table_args__ = (
        CheckConstraint(
            _literal_check("correction_type", CorrectionType),
            name="check_correction_type",
        ),
        CheckConstraint(
            _literal_check("status", CorrectionStatus),
            name="check_correction_status",
        ),
    )
```

This ensures the DB constraints always match the Python types.

---

## Design: Eliminating the Dataclass Layer

### Current architecture (three layers)

```
store.py returns:     StoredReport, StoredReportDetail, StoredExtraction,
                      StoredExtractionDetail, StoredCorrection, StoredJob
                      (frozen dataclasses)

api.py defines:       ReportResponse, ReportDetailResponse, ExtractionSummaryResponse,
                      ExtractionDetailResponse, CorrectionResponse, JobResponse
                      (Pydantic models with extra="forbid")
```

Every store method manually constructs a dataclass from SQLModel row fields. Every API endpoint
manually constructs a response model from the dataclass. That is two layers of field copying.

### Proposed architecture (two layers)

Replace the frozen dataclasses with Pydantic read models that serve **both** as store return
types and API response types:

```
store.py returns:     ReportSummary, ReportDetail, ExtractionSummary,
                      ExtractionDetail, CorrectionRecord, JobRecord
                      (Pydantic StrictBaseModel subclasses)

api.py uses:          same types as response_model
```

The API response models in `api.py` are deleted. The store's return types become the API
contract directly.

### New read models

These go in a new file `src/finding_extractor/schemas.py` (separating read/write DTOs from
the core extraction models in `models.py` and the SQLModel tables in `store.py`):

```python
"""Read-only schemas returned by the store and used as API responses.

These replace both the frozen dataclasses in store.py and the response
models in api.py, eliminating one full layer of field-by-field mapping.
"""

from finding_extractor.base import StrictBaseModel
from finding_extractor.models import (
    CorrectionStatus,
    CorrectionType,
    JobStatus,
    ReportExtraction,
    ValidationResult,
)


class ReportSummary(StrictBaseModel):
    """Report list item (no body text)."""
    id: str
    text_hash: str
    source_ref: str | None = None
    created_at: str
    seen_before: bool = False


class ReportDetail(StrictBaseModel):
    """Report with full text."""
    id: str
    text_hash: str
    report_text: str
    source_ref: str | None = None
    created_at: str


class ExtractionSummary(StrictBaseModel):
    """Extraction list item (no payload)."""
    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None = None
    created_at: str


class ExtractionDetail(StrictBaseModel):
    """Extraction with full deserialized payload."""
    id: str
    report_id: str
    model_name: str
    reasoning_effort: str | None = None
    exam_description_hint: str | None = None
    created_at: str
    extraction: ReportExtraction
    validation_result: ValidationResult | None = None


class CorrectionRecord(StrictBaseModel):
    """Persisted user correction."""
    id: str
    extraction_id: str
    target_finding_index: int | None = None
    target_json_path: str | None = None
    correction_type: CorrectionType
    status: CorrectionStatus
    comment: str | None = None
    created_by: str | None = None
    created_at: str


class JobRecord(StrictBaseModel):
    """Background job status."""
    id: str
    report_id: str
    status: JobStatus
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    extraction_id: str | None = None
    error: str | None = None
```

### Store methods use `model_validate()`

Instead of manually mapping fields from SQLModel rows to dataclasses, the store uses
Pydantic's `model_validate()` to construct read models from row attributes:

```python
# Before (store.py -- current):
async def list_reports(self, limit=50, offset=0) -> list[StoredReport]:
    ...
    return [
        StoredReport(
            id=row.id,
            text_hash=row.text_hash,
            source_ref=row.source_ref,
            created_at=row.created_at,
        )
        for row in rows
    ]

# After:
async def list_reports(self, limit=50, offset=0) -> list[ReportSummary]:
    ...
    return [ReportSummary.model_validate(row, from_attributes=True) for row in rows]
```

The `from_attributes=True` flag tells Pydantic to read values from object attributes (the
SQLModel row instance) rather than expecting a dict. This is a one-liner per method instead
of 4-8 lines of field copying.

For methods that need extra logic (like `seen_before` on report upsert, or JSON
deserialization for extraction detail), we still construct the model explicitly but only in
those specific cases.

### API endpoints become pass-through

```python
# Before (api.py -- current):
@app.get("/api/reports", response_model=list[ReportResponse])
async def list_reports(...) -> list[ReportResponse]:
    reports = await store.list_reports(limit=limit, offset=offset)
    return [
        ReportResponse(
            id=report.id,
            text_hash=report.text_hash,
            source_ref=report.source_ref,
            created_at=report.created_at,
            seen_before=report.seen_before,
        )
        for report in reports
    ]

# After:
@app.get("/api/reports", response_model=list[ReportSummary])
async def list_reports(...) -> list[ReportSummary]:
    return await store.list_reports(limit=limit, offset=offset)
```

The endpoint just returns what the store gives it. No mapping code.

---

## Detailed Change Plan

### Step 1: Create `base.py` with `StrictBaseModel`

**New file:** `src/finding_extractor/base.py`

```python
from pydantic import BaseModel, ConfigDict

class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid")
```

### Step 2: Migrate `models.py` to use `StrictBaseModel`

Change every model class:

```python
# Before:
from pydantic import BaseModel, ConfigDict

class ExamInfo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    study_description: str = Field(...)
    ...

# After:
from finding_extractor.base import StrictBaseModel

class ExamInfo(StrictBaseModel):
    study_description: str = Field(...)
    ...
```

Also move the shared Literal types here:

```python
# Add near the top of models.py:
CorrectionType = Literal["add_finding", "update_finding", "comment"]
CorrectionStatus = Literal["pending", "accepted", "rejected", "applied"]
JobStatus = Literal["pending", "running", "completed", "failed"]
Presence = Literal["present", "absent", "indeterminate", "possible"]
```

Update `ExtractedFinding.presence` to use the `Presence` alias:

```python
class ExtractedFinding(StrictBaseModel):
    ...
    presence: Presence = Field(...)
```

**Models affected:** `ExamInfo`, `FindingLocation`, `FindingAttribute`, `ExtractedFinding`,
`NonFindingText`, `ReportExtraction`, `ValidationResult` (7 classes, each loses one
`model_config` line).

### Step 3: Create `schemas.py` with read models

**New file:** `src/finding_extractor/schemas.py`

Contains: `ReportSummary`, `ReportDetail`, `ExtractionSummary`, `ExtractionDetail`,
`CorrectionRecord`, `JobRecord` (as shown above).

All inherit from `StrictBaseModel`.

### Step 4: Update `store.py`

1. **Delete all 6 frozen dataclass definitions** (`StoredReport`, `StoredReportDetail`,
   `StoredExtraction`, `StoredExtractionDetail`, `StoredCorrection`, `StoredJob`).

2. **Import read models from `schemas.py`** instead.

3. **Import `CorrectionType`, `CorrectionStatus`, `JobStatus` from `models.py`** instead of
   defining them locally.

4. **Generate CHECK constraints from Literal types** using the `_literal_check()` helper.

5. **Replace manual field mapping with `model_validate()`** in every read method:

| Method | Before (lines) | After (lines) |
|--------|----------------|---------------|
| `upsert_report` | 7-line StoredReport construction (x2) | `ReportSummary(...)` with `seen_before` logic (still explicit, ~4 lines for the new-report path, ~3 for existing) |
| `get_report` | 6-line StoredReportDetail | `ReportDetail.model_validate(row, from_attributes=True)` |
| `list_reports` | 7-line list comprehension | one-liner with `model_validate` |
| `create_extraction` | 6-line StoredExtraction | `ExtractionSummary(...)` (still explicit, ~5 lines) |
| `get_extraction` | 10-line StoredExtractionDetail | `ExtractionDetail(...)` with JSON deser (~8 lines) |
| `list_extractions` | 7-line list comprehension | one-liner with `model_validate` |
| `create_job` | 9-line StoredJob | `JobRecord.model_validate(job, from_attributes=True)` |
| `get_job` | 9-line StoredJob | `JobRecord.model_validate(row, from_attributes=True)` |
| `record_correction` | 10-line StoredCorrection | `CorrectionRecord.model_validate(...)` (~3 lines) |
| `list_corrections` | 10-line list comprehension | one-liner with `model_validate` |

**Special cases that still need explicit construction:**

- `upsert_report`: Needs `seen_before=True/False` which doesn't exist on the SQLModel row.
  We'll construct `ReportSummary(...)` explicitly here with the extra field.
- `get_extraction`: Needs to deserialize `extraction_json` and `validation_json` from strings
  to Pydantic objects. Still constructed explicitly.
- `create_extraction`: Returns summary, still explicit since we have local variables not a
  row.

### Step 5: Update `api.py`

1. **Delete all response model classes** (`ReportResponse`, `ReportDetailResponse`,
   `ExtractionSummaryResponse`, `ExtractionDetailResponse`, `CorrectionResponse`,
   `JobResponse`, `HealthResponse`). That is **7 class definitions** and ~80 lines.

2. **Import read models from `schemas.py`** and use them as `response_model`:

```python
from finding_extractor.schemas import (
    ReportSummary,
    ReportDetail,
    ExtractionSummary,
    ExtractionDetail,
    CorrectionRecord,
    JobRecord,
)
```

3. **Keep request models** (`SubmitReportRequest`, `TriggerExtractionRequest`,
   `CreateCorrectionRequest`) in `api.py` -- these are API-specific and don't appear
   elsewhere. They should also inherit from `StrictBaseModel`.

4. **Keep `HealthResponse`** -- it is tiny and API-specific. Move it to inherit from
   `StrictBaseModel`.

5. **Simplify every endpoint** to return the store result directly:

```python
# Example: list reports
@app.get("/api/reports", response_model=list[ReportSummary])
async def list_reports(...) -> list[ReportSummary]:
    return await store.list_reports(limit=limit, offset=offset)
```

6. **Job response field rename**: The current `JobResponse` has `job_id` but `StoredJob` /
   `JobRecord` has `id`. We need to either:
   - (a) Add `job_id` as a `Field(alias="id")` to `JobRecord`, or
   - (b) Change the API to return `id` instead of `job_id`.

   Option (b) is cleaner but is a **breaking API change**. Option (a) preserves
   backward-compatibility. Recommendation: go with (b) -- the extractor-ui can be updated
   simultaneously since it's in the same repo. Document the change.

   Actually, looking more carefully: `TriggerExtractionResponse` also uses `job_id`. We
   can keep this as a special request-specific model in `api.py` since it is a different
   shape (only `job_id`, `report_id`, `status` -- no timestamps). Or we can just use
   `JobRecord` for both. Recommendation: keep `TriggerExtractionResponse` as a thin model
   in `api.py` with just the three fields the 202 response needs.

### Step 6: Update `__init__.py` exports

Replace dataclass exports with schema exports:

```python
# Before:
from .store import (
    StoredCorrection, StoredExtraction, StoredExtractionDetail,
    StoredJob, StoredReport, StoredReportDetail,
)

# After:
from .schemas import (
    CorrectionRecord, ExtractionSummary, ExtractionDetail,
    JobRecord, ReportSummary, ReportDetail,
)
```

### Step 7: Update `cli.py`

The CLI uses `StorageMetadata` (a local dataclass) and `StoredReport`/`StoredExtraction` from
the store. Update to use the new schema types:

```python
# Before:
from finding_extractor.store import ExtractionStore

# After:
from finding_extractor.store import ExtractionStore
from finding_extractor.schemas import ReportSummary, ExtractionSummary
```

The `StorageMetadata` dataclass in `cli.py` is CLI-specific and can remain as-is -- it's not
part of the shared type system.

### Step 8: Update tests

Tests that import the old dataclass names need updating:

```python
# test_store.py, test_api.py -- update imports
# Old: from finding_extractor.store import StoredReport, StoredExtraction, ...
# New: from finding_extractor.schemas import ReportSummary, ExtractionSummary, ...
```

Test assertions should still pass since the field names and values are identical. The only
change is the type of the returned object (Pydantic model instead of frozen dataclass).

One behavioral difference: Pydantic models have `.model_dump()` while dataclasses have
`asdict()`. Any test using `asdict()` on store results must switch to `.model_dump()`. (A
quick grep shows `asdict` is only used on `StorageMetadata` in `cli.py`, not on store return
types in tests, so this should be minimal.)

---

## Summary of Files Changed

| File | Action | Net lines |
|------|--------|-----------|
| `src/finding_extractor/base.py` | **New** -- `StrictBaseModel` | +8 |
| `src/finding_extractor/schemas.py` | **New** -- read models | +65 |
| `src/finding_extractor/models.py` | Use `StrictBaseModel`, add shared Literal types | -10 |
| `src/finding_extractor/store.py` | Delete 6 dataclasses, use `model_validate()` | -90 |
| `src/finding_extractor/api.py` | Delete 7 response classes, simplify endpoints | -80 |
| `src/finding_extractor/__init__.py` | Update exports | ~0 |
| `src/finding_extractor/cli.py` | Update imports | ~0 |
| `tests/test_models.py` | No changes (models API unchanged) | 0 |
| `tests/test_store.py` | Update imports | ~-2 |
| `tests/test_api.py` | Update response model references | ~-5 |

**Net reduction: ~110 lines** of boilerplate mapping code.

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| API response shape changes | Use `response_model` to enforce identical JSON output. Run existing API tests. |
| `model_validate(from_attributes=True)` doesn't handle all fields | Only use for simple mappings; keep explicit construction where JSON deser is needed. |
| Import cycles (`base.py` <- `models.py` <- `schemas.py` <- `store.py`) | Strict one-way dependency: `base` -> `models` -> `schemas` -> `store`. No cycles. |
| Test breakage | All existing test logic tests field values, not type identity. Switching from dataclass to Pydantic model won't change assertions. |
| `job_id` vs `id` API change | Coordinated update in `extractor-ui/app.js`. Single repo, single PR. |

## Execution Order

1. Create `base.py` (no existing code changes, zero risk).
2. Migrate `models.py` to `StrictBaseModel` + add shared types (run `test_models.py`).
3. Create `schemas.py` (no existing code changes).
4. Update `store.py` to return schemas, delete dataclasses (run `test_store.py`).
5. Update `api.py` to use schemas as response models (run `test_api.py`).
6. Update `__init__.py` and `cli.py` imports.
7. Run full test suite (`task test`).

Each step is independently committable and testable.
