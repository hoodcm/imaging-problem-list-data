# Dev Ops Runbook

This document covers local operational setup for API + worker + Redis.

For schema change workflow details, see `docs/schema-migrations.md`.

## Compose Topology

`docker-compose.yml` defines:
1. `caddy` (`caddy:2-alpine`) — reverse proxy serving the frontend and proxying `/api/*`
2. `redis` (`redis:7.2-alpine`)
3. `api` (FastAPI process)
4. `worker` (TaskIQ worker process)

`api` and `worker` share:
- `env_file: .env`
- `IPL_DB_PATH=/data/finding_extractor.db`
- named volume `finding_extractor_db` mounted at `/data`

## Prerequisites

- Docker Desktop (or Docker Engine + Compose plugin)
- Task CLI (`task`) for project workflows in `Taskfile.yml`
- `.env` with provider credentials when running real extraction jobs

Minimum useful env:
- `OPENAI_API_KEY=...`
- optional `IPL_MODEL=openai:gpt-5-mini`

App runtime config is centralized in `src/finding_extractor/config.py`.
Configuration reference:
- `docs/configuration.md` (all `IPL_*` vars, provider key vars, `config.toml`, precedence)
- `docs/logging-usage.md` (runtime logging controls and expected fields)

## Build and Start

```bash
task stack:up
```

`task stack:up` starts Redis, runs stack migration preflight (`task db:migrate:auto:stack`), then starts API and worker with healthcheck wait.

For frontend + proxy too:

```bash
task stack:up:full
```

The `--wait` behavior blocks until service healthchecks pass (Redis responds to `PING`, API readiness responds on `/api/readyz`). The API readiness check verifies both DB access and broker-backend Redis connectivity. Service startup is ordered via `depends_on` with `condition: service_healthy`: Redis starts first, then API and worker (after Redis is healthy), then Caddy (after API is healthy).

Check status:
```bash
docker compose ps
```

Tail logs:
```bash
docker compose logs -f api worker redis
```

## Accessing the Frontend

After `task stack:up:full`, the extraction frontend is available at:

```
http://localhost:8080
```

Caddy serves the static files from `extractor-ui/` and proxies `/api/*` requests to the FastAPI backend. No `?mock` parameter is needed — the UI talks to the real backend.

## Smoke Test

```bash
task test:smoke
```

By default, `task test:smoke` uses:
- `SMOKE_MODEL=openai:gpt-5-nano`
- `SMOKE_REASONING=minimal`

You can override for your environment:

```bash
SMOKE_MODEL=openai:gpt-5-nano SMOKE_REASONING=none task test:smoke
```

Smoke flow:
1. health check
2. create report
3. trigger extraction
4. poll job until terminal state
5. fetch extraction
6. create/list correction

## Integration Test (Optional Full Stack)

```bash
task test:integration
```

These tests are intentionally outside the default fast path (`task test`) because they require Docker and provider credentials and can be slower/non-deterministic.

## Common Operations

Run local batch extraction (interactive):
```bash
uv run --env-file .env finding-extractor-batch run sample_data/example3 --glob "*.txt" --mode interactive
```

Run local batch extraction (detached) and watch:
```bash
uv run --env-file .env finding-extractor-batch run sample_data/example3 --glob "*.txt" --mode detached
uv run finding-extractor-batch status --run-id <run_id> --watch
```

Notes:
- This batch runner is local in-process and does not use TaskIQ.
- Use API + worker stack when you need broker-backed execution.

Run DB migrations to current head:
```bash
task db:migrate
```

Adopt an existing pre-Alembic DB (tables already present) without running baseline DDL:
```bash
task db:stamp:baseline
```

Run DB migrations against the Docker Compose `/data` volume:
```bash
task db:migrate:stack
```

Run stack migration preflight (upgrade head, auto-stamp baseline for pre-Alembic volumes, then upgrade):
```bash
task db:migrate:auto:stack
```

Adopt an existing pre-Alembic Docker DB volume:
```bash
task db:stamp:baseline:stack
```

Check migration status/drift:
```bash
task db:current
task db:heads
task db:check
```

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
- It means the model's output failed the verbatim-quote check after all retries (the agent retries up to 3 times via `output_retries=3`).
- The verbatim check tolerates whitespace differences (collapsed spaces, trailing newlines) but catches actual paraphrasing.
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
uv run taskiq worker --no-configure-logging finding_extractor.broker:broker finding_extractor.tasks
```
