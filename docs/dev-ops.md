# Dev Ops Runbook

This document covers local operational setup for API + worker + Redis.

## Compose Topology

`docker-compose.yml` defines:
1. `redis` (`redis:7.2-alpine`)
2. `api` (FastAPI process)
3. `worker` (TaskIQ worker process)

`api` and `worker` share:
- `env_file: .env`
- `FINDING_EXTRACTOR_DB_PATH=/data/finding_extractor.db`
- named volume `finding_extractor_db` mounted at `/data`

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- `.env` with provider credentials when running real extraction jobs

Minimum useful env:
- `OPENAI_API_KEY=...`
- optional `FINDING_EXTRACTOR_MODEL=openai:gpt-5-mini`

## Build and Start

```bash
docker compose up -d --build
```

Check status:
```bash
docker compose ps
```

Tail logs:
```bash
docker compose logs -f api worker redis
```

## Smoke Test

```bash
bash scripts/smoke_api.sh
```

Script flow:
1. health check
2. create report
3. trigger extraction
4. poll job until terminal state
5. fetch extraction
6. create/list correction

## Common Operations

Restart only API and worker:
```bash
docker compose up -d --build --force-recreate api worker
```

Stop services:
```bash
docker compose down
```

Reset state (including DB volume):
```bash
docker compose down -v
```

## Troubleshooting

### Jobs stuck in `pending`

- check worker logs: `docker compose logs --tail=200 worker`
- verify Redis connectivity and worker process health
- verify TaskIQ/FastAPI DI wiring in `src/finding_extractor/broker.py`

### Jobs fail with auth/provider errors

- verify env in running containers:
```bash
docker compose exec -T worker /bin/sh -lc 'echo "${OPENAI_API_KEY:+SET}"'
```
- ensure `.env` is loaded and key is valid

### Jobs fail with `extraction_failed:model_output_validation_failed`

- This can happen with valid credentials and healthy infra.
- It usually indicates model output did not satisfy strict extraction/output validation constraints.
- Treat as application-level extraction failure, not Redis/container outage.
- Retrying may succeed on a later run, but deterministic handling should expect this as a normal terminal failure mode.

### SQLite write issues

- confirm `/data` ownership/permissions in container
- confirm DB path is `/data/finding_extractor.db`
- if volume has stale permissions, recreate with `docker compose down -v`

## Non-Docker Local Mode

Run components separately:

Terminal 1 (Redis):
```bash
docker run --rm -p 6379:6379 redis:7.2-alpine
```

Terminal 2 (API):
```bash
uv run finding-extractor-api
```

Terminal 3 (Worker):
```bash
uv run taskiq worker finding_extractor.broker:broker finding_extractor.tasks
```
