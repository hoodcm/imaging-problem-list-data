# API Usage

This guide is for consumers of the HTTP API.

Base URL (local default):
- `http://localhost:8001`

All endpoints are under `/api`.

## Quick Start

1. Start services:
```bash
docker compose up -d --build
```

2. Submit a report:
```bash
curl -sS -X POST http://localhost:8001/api/reports \
  -H 'Content-Type: application/json' \
  -d '{"report_text":"FINDINGS: No pleural effusion.","source_ref":"example.txt"}'
```

3. Trigger extraction:
```bash
curl -sS -X POST http://localhost:8001/api/reports/<report_id>/extract \
  -H 'Content-Type: application/json' \
  -d '{}'
```

4. Poll job:
```bash
curl -sS http://localhost:8001/api/jobs/<job_id>
```

5. Fetch extraction detail when complete:
```bash
curl -sS http://localhost:8001/api/extractions/<extraction_id>
```

## Endpoints

### Health

- `GET /api/healthz`
  - process liveness

- `GET /api/readyz`
  - readiness for request serving
  - verifies database query path and queue backend connectivity
  - returns `503` when a dependency is unavailable

### Reports

- `POST /api/reports`
  - body: `{ "report_text": "...", "source_ref": "..." }`
  - returns: report row (`id`, `text_hash`, `seen_before`, ...)

- `GET /api/reports?limit=50&offset=0`
  - returns: report summary list

- `GET /api/reports/{report_id}`
  - returns: report detail including full `report_text`

### Extractions and Jobs

- `POST /api/reports/{report_id}/extract`
  - optional body fields: `model`, `reasoning`, `exam_description`, `validate`
  - returns `202` with `job_id`
  - response headers include:
    - `Location: /api/jobs/{job_id}`
    - `Retry-After: 2`

- `GET /api/jobs/{job_id}`
  - status values: `pending`, `running`, `completed`, `failed`
  - on completed: includes `extraction_id`

- `GET /api/reports/{report_id}/extractions`
  - returns extraction summaries for that report

- `GET /api/extractions/{extraction_id}`
  - returns full extraction payload and optional validation result

### Corrections

- `POST /api/extractions/{extraction_id}/corrections`
- `GET /api/extractions/{extraction_id}/corrections`
- invalid correction payloads return `422` with a validation detail message

Common MVP correction payload (comment):
```json
{
  "correction_type": "comment",
  "comment": "Looks good",
  "created_by": "reviewer@example.org"
}
```

For `correction_type="update_finding"`:
- include `target_finding_index` or `target_json_path`
- if `target_finding_index` is provided, it must reference an existing finding in that extraction; otherwise the API returns `422`

## Job Error Codes

`jobs.error` is a sanitized public field.

Current values:
- `enqueue_failed:queue_unavailable`
- `extraction_failed:invalid_request`
- `extraction_failed:model_provider_error`
- `extraction_failed:model_output_validation_failed`
- `extraction_failed:model_timeout`
- `extraction_failed:internal_error`

Do not parse provider-specific internal messages from this field.

## Polling and Retry Contract

Recommended client behavior for `POST /api/reports/{id}/extract` + `GET /api/jobs/{job_id}`:
1. Read `Location` and `Retry-After` from trigger response.
2. Poll the job endpoint using `Retry-After` (fallback to 2 seconds).
3. Treat `pending`/`running` as non-terminal.
4. Treat `completed`/`failed` as terminal.
5. Apply a client timeout budget (for example 1-5 minutes) and allow user retry on timeout.

`failed` is an expected terminal outcome; do not assume all jobs complete successfully.

## Real-Model Variability

With live model providers, extraction can fail even with valid credentials and healthy infrastructure.
One common terminal error code is:
- `extraction_failed:model_output_validation_failed`

This generally indicates model output failed strict validation/retry constraints, not queue/container failure.

## Planned Endpoint Status

`GET /api/models` is planned but not implemented yet.
Current model/provider selection is environment-driven (`FINDING_EXTRACTOR_MODEL` plus available provider credentials).

## CORS

Configure allowed origins with:
- `FINDING_EXTRACTOR_CORS_ORIGINS`
- comma-separated list (e.g. `http://localhost:3000,http://localhost:5173`)

## OpenAPI

Interactive docs are available at:
- `http://localhost:8001/docs`
