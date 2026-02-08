# Plan: FastAPI Wrapper for Finding Extractor

## Context

The persistence layer (`ExtractionStore`) is nearly committed. The next step is exposing it via a FastAPI JSON API so a frontend can submit reports, trigger extractions, and browse results. Extractions call an LLM and can take seconds to minutes, so we need background task processing via **TaskIQ with a Redis broker**.

All persisted IDs in this API are **UUID strings** (`str`), matching the current store schema.

## SQLite Concurrency (WAL Mode)

Both the API and the worker process read/write the same SQLite database. This is safe with proper configuration — Rails 8 ships this pattern in production, and Apache Airflow recently dropped its single-process SQLite restriction in favor of WAL mode.

**Required PRAGMAs** (set on every new connection via SQLAlchemy `connect` event):

| PRAGMA | Value | Why |
|--------|-------|-----|
| `journal_mode` | `WAL` | Concurrent readers + single writer; readers never block writers |
| `busy_timeout` | `5000` | Wait up to 5s for write lock instead of failing immediately |
| `synchronous` | `NORMAL` | Safe with WAL; avoids fsync on every commit |
| `foreign_keys` | `ON` | Off by default in SQLite |

```python
@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()
```

**Docker volume note:** Named volumes on the same Docker host share a single kernel, so POSIX file locking and the WAL shared-memory file (`-shm`) work correctly. This does **not** work across hosts (NFS, EFS, multi-node Kubernetes), which is not a concern for this project.

**Write transaction note:** Keep write transactions short (commit per extraction, not per batch). Long-held write locks force other writers to wait up to `busy_timeout`.

## Background Tasks: TaskIQ + Redis

**Packages** (all actively maintained, Feb 2026):

| Package | Version | Purpose |
|---------|---------|---------|
| `taskiq` | 0.12.1 | Core async task framework |
| `taskiq-redis` | 1.2.2 | Redis stream broker + result backend |
| `taskiq-fastapi` | 0.4.0 | FastAPI dependency injection in workers |

**How it works:**
- Broker defined in `broker.py` (importable by worker CLI)
- Tasks decorated with `@broker.task` in `tasks.py`
- FastAPI endpoint generates a `job_id` UUID, creates a pending job row, then dispatches `run_extraction.kiq(job_id, ...)`
- Use a single identifier concept: API `job_id` is the task identity passed through the worker payload
- Status polling endpoint reads the SQLite `jobs` table (`store.get_job`) as source of truth
- Worker process started separately: `taskiq worker finding_extractor.broker:broker finding_extractor.tasks`
- `taskiq_fastapi.init(broker, "finding_extractor.api:app")` lets tasks access `app.state.store` via DI
- Unit tests use `InMemoryBroker` for fast local DX (no Redis required); optional integration tests use Redis-backed broker

**Running locally requires Redis:**
```bash
docker run -d -p 6379:6379 redis:latest   # or brew services start redis
```

## New Dependencies

**Runtime** (`[project].dependencies`):
```
"fastapi>=0.115.0",
"uvicorn[standard]>=0.34.0",
"taskiq>=0.12.0",
"taskiq-redis>=1.2.0",
"taskiq-fastapi>=0.4.0",
```

**Dev** (`[dependency-groups].dev`):
```
"httpx>=0.28.0",
```

**New script entries** (`[project.scripts]`):
```
finding-extractor-api = "finding_extractor.api:main"
```

## Containerization Strategy

Use one container image for both runtime roles, selected by container command:

- API role command:
  - `uv run finding-extractor-api`
- Worker role command:
  - `uv run taskiq worker finding_extractor.broker:broker finding_extractor.tasks`

### Dockerfile

- Create a single `Dockerfile` for the project.
- Install runtime dependencies only.
- Default `CMD` can be API (`uv run finding-extractor-api`), while Compose overrides command for workers.

### Docker Compose Ensemble

Create `docker-compose.yml` with 3 services:

- `redis`
  - Image: `redis:7-alpine`
  - Expose `6379`
- `api`
  - Build from local `Dockerfile`
  - Command: `uv run finding-extractor-api`
  - Ports: `8001:8001`
  - Env:
    - `FINDING_EXTRACTOR_REDIS_URL=redis://redis:6379`
    - `FINDING_EXTRACTOR_DB_PATH=/data/finding_extractor.db`
  - Mount dedicated DB volume at `/data`
  - Depends on `redis`
- `worker`
  - Build from local `Dockerfile` (same image as API)
  - Command: `uv run taskiq worker finding_extractor.broker:broker finding_extractor.tasks`
  - Env:
    - `FINDING_EXTRACTOR_REDIS_URL=redis://redis:6379`
    - `FINDING_EXTRACTOR_DB_PATH=/data/finding_extractor.db`
    - LLM API keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.) and `FINDING_EXTRACTOR_MODEL` as needed
  - Mount same dedicated DB volume at `/data`
  - Depends on `redis`

Named volumes:
- `finding_extractor_db` (dedicated SQLite volume, mounted at `/data`)

Minimal compose shape:
```yaml
services:
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
  api:
    build: .
    command: uv run finding-extractor-api
    ports: ["8001:8001"]
    environment:
      FINDING_EXTRACTOR_REDIS_URL: redis://redis:6379
      FINDING_EXTRACTOR_DB_PATH: /data/finding_extractor.db
    volumes:
      - finding_extractor_db:/data
    depends_on: [redis]
  worker:
    build: .
    command: uv run taskiq worker finding_extractor.broker:broker finding_extractor.tasks
    environment:
      FINDING_EXTRACTOR_REDIS_URL: redis://redis:6379
      FINDING_EXTRACTOR_DB_PATH: /data/finding_extractor.db
    volumes:
      - finding_extractor_db:/data
    env_file: .env  # LLM API keys (OPENAI_API_KEY, ANTHROPIC_API_KEY, etc.)
    depends_on: [redis]

volumes:
  finding_extractor_db:
```

## API Endpoints (9 total, all under `/api/`)

### Reports
| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `POST` | `/api/reports` | Submit/upsert report text | 200 |
| `GET` | `/api/reports` | List reports (paginated) | 200 |
| `GET` | `/api/reports/{report_id}` | Get single report with text | 200/404 |

### Extractions & Jobs
| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `POST` | `/api/reports/{report_id}/extract` | Dispatch TaskIQ extraction job | 202 |
| `GET` | `/api/jobs/{job_id}` | Poll job status/result | 200/404 |
| `GET` | `/api/reports/{report_id}/extractions` | List extractions for report | 200 |
| `GET` | `/api/extractions/{extraction_id}` | Get full extraction detail | 200/404 |

### Corrections
| Method | Path | Description | Status |
|--------|------|-------------|--------|
| `POST` | `/api/extractions/{extraction_id}/corrections` | Add correction | 201 |
| `GET` | `/api/extractions/{extraction_id}/corrections` | List corrections | 200 |

## Files to Create/Modify

### New: `src/finding_extractor/broker.py`
Small module defining the TaskIQ broker — must be independently importable for the worker CLI.
```python
import os
from taskiq_redis import RedisAsyncResultBackend, RedisStreamBroker

_redis_url = os.getenv("FINDING_EXTRACTOR_REDIS_URL", "redis://localhost:6379")

result_backend = RedisAsyncResultBackend(redis_url=_redis_url, result_ex_time=3600)
broker = RedisStreamBroker(url=_redis_url).with_result_backend(result_backend)
```

### New: `src/finding_extractor/tasks.py`
Single extraction task using `@broker.task`. Uses a worker-safe dependency (`get_task_store`) via `TaskiqDepends`:
```python
@broker.task
async def run_extraction(
    job_id: str,
    report_id: str,
    model: str | None = None,
    reasoning: str | None = None,
    exam_description: str | None = None,
    validate: bool = True,
    store: ExtractionStore = TaskiqDepends(get_task_store),
) -> dict:
    # 0. store.mark_job_running(job_id)  — job row already exists (created before dispatch)
    # 1. Fetch report from store
    # 2. Call extract_findings()
    # 3. Optionally validate_extraction()
    # 4. store.create_extraction()
    # 5. store.mark_job_completed(job_id, extraction_id=...)
    #    or store.mark_job_failed(job_id, error=...)
    # 6. Return {"extraction_id": ..., "model_name": ...}
```

### New: `src/finding_extractor/api.py`
FastAPI application containing:
1. **Pydantic request/response models** — `SubmitReportRequest`, `TriggerExtractionRequest`, `CreateCorrectionRequest`, and response models
2. **App factory** — `create_app(store=None, broker=None)` with lifespan that:
   - Creates/injects `ExtractionStore` into `app.state.store`
   - Uses provided broker or imports default from `broker.py`; tests pass `InMemoryBroker`
   - Calls `broker.startup()` / `broker.shutdown()` (guarded by `if not broker.is_worker_process`)
   - Calls `taskiq_fastapi.init(broker, "finding_extractor.api:app")`
   - Calls `await app.state.store.close()` on shutdown (always explicit cleanup)
3. **Dependencies**
   - `get_store(request: Request) -> ExtractionStore` for HTTP routes
   - `get_task_store(request: Annotated[Request, TaskiqDepends()]) -> ExtractionStore` for TaskIQ worker tasks
4. **9 route handlers** — thin wrappers calling store methods
5. **CORS middleware** — env-configurable origins for frontend
6. **`main()` entry point** — runs uvicorn on port 8001

Key extraction dispatch pattern:
```python
@app.post("/api/reports/{report_id}/extract", status_code=202)
async def trigger_extraction(report_id: str, body: TriggerExtractionRequest, response: Response, ...):
    report = await store.get_report(report_id)  # verify exists, 404 if not
    job_id = str(uuid.uuid4())
    await store.create_job(job_id=job_id, report_id=report_id, status="pending")
    try:
        await run_extraction.kiq(job_id, report_id, body.model, body.reasoning, ...)
    except Exception as e:
        # Minimal MVP reliability: do not leave a permanently pending job on enqueue failure.
        await store.mark_job_failed(job_id, error=f"enqueue_failed: {e}")
        raise HTTPException(status_code=503, detail="Failed to enqueue extraction job")
    response.headers["Location"] = f"/api/jobs/{job_id}"
    response.headers["Retry-After"] = "2"
    return {"job_id": job_id, "report_id": report_id, "status": "pending"}

@app.get("/api/jobs/{job_id}")
async def get_job_status(job_id: str):
    job = await store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
```

### Modify: `src/finding_extractor/store.py`
Add WAL pragmas, read APIs, and explicit job tracking:

- Add SQLAlchemy `connect` event listener to set WAL pragmas (see SQLite Concurrency section above)

- Keep current write-return models (`StoredReport`, `StoredExtraction`) for create/upsert paths.
- Add read-focused detail models:
  - `StoredReportDetail` (includes `report_text`)
  - `StoredExtractionDetail` (includes deserialized `ReportExtraction` and optional `ValidationResult`)
- Add read methods:
  - `get_report(report_id: str) -> StoredReportDetail | None`
  - `list_reports(limit=50, offset=0) -> list[StoredReport]`
  - `get_extraction(extraction_id: str) -> StoredExtractionDetail | None`
  - `list_extractions(report_id: str) -> list[StoredExtraction]`
- Add lightweight job lifecycle persistence in SQLite so we can distinguish `404` unknown jobs from `pending` jobs:
  - `create_job(job_id: str, report_id: str, status: Literal["pending", "running", "completed", "failed"])`
  - `get_job(job_id: str) -> StoredJob | None`
  - `mark_job_running(job_id: str)`
  - `mark_job_completed(job_id: str, extraction_id: str)`
  - `mark_job_failed(job_id: str, error: str)`

### New: `tests/test_api.py`
- Uses `InMemoryBroker` as a test mock (no Redis required for unit tests)
- Async httpx `ASGITransport` client fixture using `create_app(store=temp_store)`
- Monkeypatched `extract_findings` for extraction task tests
- Tests for all 9 endpoints including 404 cases and deduplication
- Includes enqueue-failure test (assert no stuck `pending` job and 503 response)

### Modify: `pyproject.toml`
- Add `fastapi`, `uvicorn[standard]`, `taskiq`, `taskiq-redis`, `taskiq-fastapi` to runtime deps
- Add `httpx` to dev deps
- Add `finding-extractor-api` script entry

### New: `Dockerfile`
- Single runtime image usable for either API or worker roles
- Default command runs API; worker command is provided by Compose/service override

### New: `docker-compose.yml`
- Defines `redis`, `api`, and `worker` services
- Uses a dedicated named volume for SQLite DB storage (`finding_extractor_db`)
- Mounts DB volume at `/data` and sets `FINDING_EXTRACTOR_DB_PATH=/data/finding_extractor.db`

### New: `.dockerignore`
- Exclude virtualenvs, caches, git metadata, test artifacts, and local DB files from image build context

### Modify: `src/finding_extractor/__init__.py`
- Export new store return types if any new dataclasses are added

## Implementation Sequence

1. **Add store read/detail methods and job tracking methods** to `store.py` + tests in `test_store.py`
2. **Create `broker.py`** — Redis broker + result backend config
3. **Create `tasks.py`** — `run_extraction` task with worker-safe store DI + job lifecycle updates
4. **Create `api.py`** — app factory, lifespan (broker startup/shutdown + store init/close), CORS, route/task dependencies
5. **Implement report endpoints** (POST, GET list, GET detail)
6. **Implement extraction read endpoints** (GET list, GET detail)
7. **Implement job dispatch/status endpoints** (POST trigger via `kiq()` + `Location`/`Retry-After`, GET status via job table, mark failed on enqueue exception)
8. **Implement correction endpoints** (POST, GET list)
9. **Write `tests/test_api.py`** with `InMemoryBroker` default; add optional Redis integration tests separately
10. **Add container artifacts** (`Dockerfile`, `.dockerignore`, `docker-compose.yml`) with shared image + dedicated DB volume
11. **Update `pyproject.toml`** and `__init__.py`

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| Task queue | TaskIQ + Redis | Persistent job state, retries, result tracking, async-native |
| Broker type | `RedisStreamBroker` | Message acknowledgement prevents loss during worker failures |
| Result backend | `RedisAsyncResultBackend` | Built-in result storage with TTL expiry |
| File structure | `broker.py` + `tasks.py` + `api.py` | Broker must be independently importable for worker CLI |
| App creation | Factory `create_app(store=None, broker=None)` | Clean test injection; tests pass `InMemoryBroker` + temp store |
| Worker DI | `taskiq-fastapi` + dedicated `get_task_store` | Reuses FastAPI app state in worker without custom wiring |
| SQLite concurrency | WAL mode + `busy_timeout=5000` | Proven multi-process pattern (Rails 8, Airflow); sufficient for low-traffic API + single worker |
| Test broker | `InMemoryBroker` for unit tests | No Redis dependency for `pytest`; integration tests can use Redis separately |
| Job ID strategy | Single ID (`job_id`) generated by API | One identifier across frontend/API/worker simplifies tracing and routing |
| Job status source of truth | SQLite `jobs` table | Allows clear distinction between unknown job (`404`) and pending job (`200`) |
| Container runtime | One image, role by command | Reduces drift between API and worker environments |
| DB persistence volume | Named Docker volume at `/data` | Dedicated persistent storage for SQLite file across restarts |
| Port | 8001 default | Avoids conflict with viewer on 8000 |
| ID types | UUID strings (`str`) | Matches existing `ExtractionStore` schema and CLI metadata |

## Job Status Semantics (HTTP)

Recommended semantics for async job APIs:

- `POST /api/reports/{report_id}/extract`
  - Return `202 Accepted`
  - Include `Location: /api/jobs/{job_id}` and `Retry-After: 2`
  - Body includes `job_id` and initial `status: "pending"`
- `GET /api/jobs/{job_id}`
  - `404 Not Found`: job ID is unknown (never created or pruned from retention window)
  - `200 OK` + `status: "pending"` or `"running"`: accepted but not completed
  - `200 OK` + `status: "completed"`: includes `extraction_id` (+ optional metadata)
  - `200 OK` + `status: "failed"`: includes stable error summary

Notes:
- `202` is explicitly non-committal and indicates processing may not have started yet.
- To reliably return `404` for unknown jobs (instead of conflating with pending), track dispatched jobs explicitly (`jobs` table).
- If enqueue fails after creating the pending row, mark the job as `failed` and return `503` (prevents stuck `pending` jobs).

## Verification

1. **Unit tests:** `uv run pytest tests/test_api.py tests/test_store.py -v`
2. **Container smoke test (recommended):**
   ```bash
   docker compose up --build -d
   curl http://localhost:8001/api/reports
   docker compose logs -f api worker
   ```
   ```bash
   # Verify DB file exists in dedicated volume mount
   docker compose exec api ls -la /data
   ```
3. **Manual smoke test (4 terminals):**
   ```bash
   # Terminal 1: Redis
   docker run -p 6379:6379 redis:latest

   # Terminal 2: API server
   uv run finding-extractor-api   # starts on :8001

   # Terminal 3: TaskIQ worker
   uv run taskiq worker finding_extractor.broker:broker finding_extractor.tasks --reload
   ```
   ```bash
   # Terminal 4: Test calls
   curl -X POST http://localhost:8001/api/reports \
     -H 'Content-Type: application/json' \
     -d '{"report_text": "FINDINGS: Normal heart size..."}'

   curl http://localhost:8001/api/reports

   curl -X POST http://localhost:8001/api/reports/<report_uuid>/extract \
     -H 'Content-Type: application/json' -d '{}'
   # Returns: {"job_id": "abc-123", "status": "pending"}

   curl http://localhost:8001/api/jobs/abc-123
   # Returns: {"job_id": "abc-123", "status": "completed", "extraction_id": "<extraction_uuid>"}
   ```
4. **OpenAPI docs:** Visit `http://localhost:8001/docs` for auto-generated Swagger UI
