# API Internals

This guide is for maintainers changing API/worker behavior.

## Modules

- `src/finding_extractor/api.py`
  - FastAPI app factory and HTTP route handlers
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
2. initializes DB schema (`store.init()`)
3. starts broker if not a worker process
4. shuts broker down on app shutdown
5. closes store explicitly

Tests inject `InMemoryBroker` and temp store for deterministic behavior.

## Job Lifecycle Contract

Expected transitions:
- API enqueue path: `pending`
- worker starts: `running`
- success: `completed` + `extraction_id`
- failure: `failed` + sanitized `error`

Unknown job IDs return `404` at `GET /api/jobs/{job_id}`.

## Error Handling Strategy

### Enqueue failure (API process)

If `.kiq(...)` fails:
- job is marked failed with `enqueue_failed:queue_unavailable`
- endpoint returns `503`

### Task failure (worker process)

Task exceptions are mapped to stable public error codes via `to_public_job_error(...)`.
Raw exception content is logged, not exposed through API payloads.

## Dependency Injection and Worker Context

Worker task DI depends on TaskIQ/FastAPI context being initialized in `broker.py`:

```python
taskiq_fastapi.init(broker, "finding_extractor.api:app")
```

This is required because worker CLI imports broker module directly.

## Data Model and Serialization

Route response models in `api.py` are explicit Pydantic models.
Store layer returns dataclasses and deserialized domain models.

`extractions.extraction_json` and `extractions.validation_json` store full payload snapshots.

## Testing Model

- Unit/integration-lite tests:
  - `tests/test_api.py`
  - `tests/test_store.py`
  - `tests/test_tasks.py`
- Current gap:
  - no CI test that boots real worker process + Redis broker end-to-end.
  - this means worker-process DI regressions and cross-process queue/runtime issues may bypass CI until we add container/worker integration coverage.
