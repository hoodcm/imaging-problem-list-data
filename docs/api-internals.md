# API Internals

This guide is for maintainers changing API/worker behavior.

## Modules

- `src/finding_extractor/api.py`
  - FastAPI app factory, lifecycle wiring, health/readiness endpoints
- `src/finding_extractor/api_routes.py`
  - report/extraction/job/correction route handlers (`/api/*`)
- `src/finding_extractor/api_services.py`
  - API orchestration helpers (resource lookup, enqueue flow)
- `src/finding_extractor/api_models.py`
  - request/response contract models and store->response mapping helpers
- `src/finding_extractor/api_dependencies.py`
  - shared FastAPI dependencies (`get_store`, `get_model_catalog_service`)
- `src/finding_extractor/model_catalog.py`
  - provider model discovery + SOTA filtering + Redis catalog cache
- `src/finding_extractor/model_policy.py`
  - shared model-id parsing and policy validation (`validate_model_id`)
- `src/finding_extractor/broker.py`
  - Redis TaskIQ broker and result backend
  - TaskIQ/FastAPI integration initialization
- `src/finding_extractor/tasks.py`
  - Background extraction task implementation
- `src/finding_extractor/store.py`
  - persistence and job lifecycle state transitions

## Runtime Roles

- API process:
  - serves HTTP
  - writes initial `jobs` rows
  - enqueues TaskIQ jobs
- Worker process:
  - consumes queued jobs
  - executes extraction
  - updates `jobs` state and persists extraction rows

## App Lifecycle

`create_app(store=None, broker=None)`:
1. creates/injects `ExtractionStore`
2. creates `ModelCatalogService` for `/api/models`
3. initializes DB schema (`store.init()`)
4. starts broker if not a worker process
5. shuts broker down on app shutdown
6. closes model catalog Redis client
7. closes store explicitly

Tests inject `InMemoryBroker` and temp store for deterministic behavior.

## Job Lifecycle Contract

Expected transitions:
- API enqueue path: `pending`
- worker starts: `running`
- success: `completed` + `extraction_id`
- success with deterministic warnings: `completed_with_warnings` + `extraction_id` + `warning_payload`
- failure: `failed` + sanitized `error`

Unknown job IDs return `404` at `GET /api/jobs/{job_id}`.

## Error Handling Strategy

### Enqueue failure (API process)

If `.kiq(...)` fails:
- job is marked failed with `enqueue_failed:queue_unavailable`
- endpoint returns `503`

### Model policy and reasoning validation (API process)

`POST /api/reports/{id}/extract` validates:
1. The effective model id (`body.model` or configured default) — policy violations return `422`.
2. The reasoning level (if provided) — invalid values or incompatible model+reasoning combos return `422`. Validation uses `validate_reasoning_for_model()` from `agent.py`, which checks both the level itself and provider compatibility (e.g., Ollama only supports `reasoning="none"`).

### Task failure (worker process)

Task exceptions are mapped to stable public error codes via `to_public_job_error(...)`.
Raw exception content is logged, not exposed through API payloads.
Worker execution re-validates model policy as defense in depth and maps policy violations to
`extraction_failed:invalid_request`.
Strict reliability mode failures map to:
- `extraction_failed:validation_failed` for validation failures
- `extraction_failed:section_failures_remaining` for unrecovered modular section failures

### Reliability mode and warnings contract

`POST /api/reports/{id}/extract` accepts `reliability_mode` (`strict` default, `lenient` optional).

- `strict`:
  - validation errors are terminal failures (`error=extraction_failed:validation_failed`)
  - unrecovered modular section failures are terminal failures (`error=extraction_failed:section_failures_remaining`)
  - deterministic `warning_payload` is still included on the failed job record
- `lenient`:
  - invalid spans are dropped before persistence
  - job is marked `completed_with_warnings`
  - `warning_payload` includes dropped counts and ordered reason categories
  - `warning_payload.section_failure_count` carries unrecovered modular section failures
  - worker logs emit `Reliability contract outcome` with terminal status and warning counters for alerting/monitoring sinks

### Correction validation failure (API process)

`POST /api/extractions/{id}/corrections` converts store-layer `ValueError` validation failures to `422`.
For `update_finding`, an out-of-range `target_finding_index` is rejected with `422` instead of storing an unanchored correction.

## Health and Readiness Contract

- `GET /api/healthz`
  - process-level liveness only
- `GET /api/readyz`
  - verifies DB access path via `store.list_reports(limit=1, offset=0)`
  - verifies queue backend availability by pinging Redis through the broker connection pool
  - returns `503` if either dependency check fails

## Model Catalog Behavior

- `/api/models` is lazy-refreshed; app startup does not proactively fetch provider model lists.
- Cache storage is Redis (`finding_extractor:model_catalog:v2`).
- Refresh lock uses Redis `SET NX EX` to avoid concurrent refresh storms.
- Superseded generations are filtered out by selecting latest version per provider tier/family.

## Dependency Injection and Worker Context

Worker task DI depends on TaskIQ/FastAPI context being initialized in `broker.py`:

```python
taskiq_fastapi.init(broker, "finding_extractor.api:app")
```

This is required because worker CLI imports broker module directly.

## Data Model and Serialization

Route request/response models are in `api_models.py` and remain explicit Pydantic models.
Store layer returns dataclasses and deserialized domain models.

`extractions.extraction_json` and `extractions.validation_json` store full payload snapshots.

Token usage is stored in dedicated nullable columns on the `extractions` table (`input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `model_requests`, `duration_ms`) for direct SQL analytics, plus `usage_details_json` for provider-specific extras. The store layer reconstructs an `ExtractionUsage` Pydantic model from these columns via `_usage_from_row()`.

API response models `ExtractionSummaryResponse` and `ExtractionDetailResponse` include a `usage: ExtractionUsage | None` field, mapped from stored extraction data. The field is `null` for older extractions or providers that don't report usage.

## Testing Model

- Unit/integration-lite tests:
  - `tests/test_api.py`
  - `tests/test_store.py`
  - `tests/test_tasks.py`
- Current gap:
  - no CI test that boots real worker process + Redis broker end-to-end.
  - this means worker-process DI regressions and cross-process queue/runtime issues may bypass CI until we add container/worker integration coverage.
