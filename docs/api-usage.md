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
  -d '{"report_text":"FINDINGS: No pleural effusion.","source_ref":"example.txt","patient_id":"MRN0000001"}'
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
  - body: `{ "report_text": "...", "source_ref": "...", "patient_id": "..." }`
  - `patient_id` is optional, for associating reports with patients
  - returns: report row (`id`, `text_hash`, `patient_id`, `seen_before`, ...)

- `GET /api/reports?limit=50&offset=0`
  - returns: report summary list (includes `patient_id` if present)

- `GET /api/reports/{report_id}`
  - returns: report detail including full `report_text` and `patient_id`

### Users

- `GET /api/users`
  - returns: list of registered users for correction attribution
  - response: `[{ "username": "...", "name": "...", "email": "..." }]`
  - no pagination (small dataset expected)

### Extractions and Jobs

- `GET /api/models`
  - returns currently available, SOTA-filtered model IDs by provider
  - includes explicit provider policy filtering:
    - Anthropic: only version `4.5` and `4.6` models
    - Google Gemini: only `gemini-3*` `pro`/`flash` models
  - response includes:
    - `updated_at`: ISO timestamp of last catalog refresh
    - `stale`: true when the API had to serve stale/fallback catalog data
    - `refresh_interval_seconds`: configured refresh interval
    - `models`: list of `{ id, provider, tier, is_default }`
  - model IDs are directly usable in `POST /api/reports/{report_id}/extract` (`model` field)

- `POST /api/reports/{report_id}/extract`
  - optional body fields: `model`, `reasoning`, `exam_description`, `validate`
  - `reasoning` must be one of: `none`, `minimal`, `low`, `medium`, `high`
  - returns `202` with `job_id`
  - returns `422` for:
    - model-policy violations (e.g., `google-vertex:*` is rejected; use `google-gla:*`)
    - invalid reasoning values (e.g., `"turbo"`)
    - incompatible model+reasoning combinations (e.g., `ollama:*` with `reasoning="high"`)
  - response headers include:
    - `Location: /api/jobs/{job_id}`
    - `Retry-After: 2`

- `GET /api/jobs/{job_id}`
  - status values: `pending`, `running`, `completed`, `failed`
  - on completed: includes `extraction_id`

- `GET /api/reports/{report_id}/extractions`
  - returns extraction summaries for that report
  - each summary includes `usage` (nullable) with token counts and duration

- `GET /api/extractions/{extraction_id}`
  - returns full extraction payload, optional validation result, and optional usage
  - `usage` object (when present):
    ```json
    {
      "requests": 1,
      "input_tokens": 500,
      "output_tokens": 200,
      "cache_read_tokens": 50,
      "cache_write_tokens": 100,
      "duration_ms": 1234,
      "details": {}
    }
    ```
  - `usage` is `null` for extractions created before usage tracking or from providers that don't report it

### Corrections

- `POST /api/extractions/{extraction_id}/corrections`
  - body must include `username` (required) for correction attribution
  - `username` is validated against registered users; returns `400` if invalid
  - response includes:
    - `author`: structured object with `{ username, name, email }` for attributed corrections
    - `created_by`: legacy fallback (always `null` for new corrections)
- `GET /api/extractions/{extraction_id}/corrections`
  - returns list of corrections with structured `author` field
  - legacy corrections (no `username`) will have `author: null` and `created_by` as free-text fallback
- invalid correction payloads return `422` with a validation detail message

Common MVP correction payload (comment):
```json
{
  "correction_type": "comment",
  "comment": "Looks good",
  "username": "talkasab"
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

## Model Discovery Refresh

`GET /api/models` uses Redis-backed caching and refreshes on-demand at most once per:
- `IPL_MODEL_LIST_UPDATE_INTERVAL` (default `172800` seconds / 48 hours)

If discovery fails during refresh, the API may return stale cached results (`stale: true`) or a default-model fallback entry.
If Redis is unavailable, the endpoint still responds with a stale-marked uncached discovery/fallback payload.

Configuration reference:
- `docs/configuration.md`

## CORS

Configure allowed origins with:
- `IPL_CORS_ORIGINS`
- comma-separated list (e.g. `http://localhost:3000,http://localhost:5173`)

Configuration reference:
- `docs/configuration.md`

## OpenAPI

Interactive docs are available at:
- `http://localhost:8001/docs`
