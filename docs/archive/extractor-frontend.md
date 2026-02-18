# Extraction Frontend Plan (MVP First)

## Goal
Build a lightweight static frontend for the extraction API using Alpine.js, with zero build step, that is simple enough for a junior engineer to implement directly.

This document is split into:
- MVP implementation steps (explicit, sequential, handoff-ready)
- Post-MVP expected issues (likely next work, but intentionally not over-specified)

## Stack and Constraints
- Alpine.js 3.x for state and view switching
- Tailwind CSS v4 + Flowbite 4.0.1 via CDN
- Static files only (`extractor-ui/index.html`, `extractor-ui/app.js`)
- Hash routing only (`#/...`)
- API base path: `/api`

## MVP Scope
### In scope
- Submit report
- Submit report and immediately trigger extraction
- List reports
- View report detail and prior extractions
- Trigger extraction from report detail
- Poll extraction job status until complete/failed
- View extraction detail
- Create and list comment corrections
- Global error banner, loading states, dark mode toggle

### Out of scope (MVP)
- Full structured correction editing (`add_finding` and `update_finding` forms)
- Advanced pagination UX (jump-to-page, total count)
- Auth/roles
- Realtime push (SSE/WebSocket)

## Files to Create
```text
extractor-ui/
  index.html
  app.js
```

## API Contract (MVP Reference)
Use these endpoints exactly:

| Method | Path | Purpose | MVP Usage |
|---|---|---|---|
| POST | `/api/reports` | Submit/upsert report | Required |
| GET | `/api/reports` | List reports | Required |
| GET | `/api/reports/{report_id}` | Report detail | Required |
| POST | `/api/reports/{report_id}/extract` | Trigger extraction job | Required |
| GET | `/api/jobs/{job_id}` | Poll job status | Required |
| GET | `/api/reports/{report_id}/extractions` | List extraction summaries | Required |
| GET | `/api/extractions/{extraction_id}` | Extraction detail | Required |
| POST | `/api/extractions/{extraction_id}/corrections` | Create correction | MVP: comment only |
| GET | `/api/extractions/{extraction_id}/corrections` | List corrections | Required |

### Request/response shapes to implement
`POST /api/reports` request body:
```json
{
  "report_text": "string (required)",
  "source_ref": "string or null"
}
```

`POST /api/reports/{id}/extract` request body (MVP):
```json
{
  "exam_description": "string or null"
}
```
If no exam description is entered, send `{}`.
If this endpoint returns `503`, treat it as enqueue failure: show an error banner and keep the user on the current page (do not navigate to extracting view).

`POST /api/extractions/{id}/corrections` request body (MVP comment mode):
```json
{
  "correction_type": "comment",
  "comment": "string (required)",
  "created_by": "string or null"
}
```

`GET /api/jobs/{id}` expected statuses:
- `pending`
- `running`
- `completed` (must include `extraction_id`)
- `failed` (may include `error`)

## Routing Contract
Use hash routes:

```text
#/                                 submit view
#/reports                          reports list
#/reports/{report_id}              report detail
#/reports/{report_id}/extracting/{job_id}   extraction progress
#/extractions/{extraction_id}      extraction detail
```

Any unknown route should redirect to `#/`.

## MVP Implementation Steps (Do in Order)

### 1. Bootstrap page shell (`index.html`) — DONE
Tasks:
- Include Tailwind CDN, Flowbite CSS/JS, Alpine CDN.
- Add dark-mode initialization script before render.
- Add `<div x-data="extractorApp()" x-init="init()">`.
- Add top navigation with links to `#/` and `#/reports`.
- Add global error banner component.
- Add `x-cloak` style.

### 2. Create base app state and router (`app.js`) — DONE
Tasks:
- Define single Alpine scope with all state fields.
- Implement `init()`, `navigate(view, params)`, `navigateFromHash()`.
- On route change, clear stale async state and stop active polling timer.

### 3. Add shared API helper — DONE
Tasks:
- `apiFetch(path, options)` with JSON headers, error parsing, status-code-aware throws.
- Mock mode via `?mock` URL parameter delegates to `mockApiFetch()`.

### 4. Implement Submit view — DONE
Tasks:
- Report text (required), source ref, exam description, model, reasoning fields.
- Submit Report and Submit & Extract buttons.
- 503 handling on extract trigger.
- Client-side validation for empty report text.

### 5. Implement Reports list view — DONE
Tasks:
- Table with truncated ID, source ref, created_at.
- Row click navigation, refresh button, prev/next pagination.

### 6. Implement Report detail view — DONE
Tasks:
- Report metadata and text display.
- Run Extraction with model/reasoning options.
- Extractions table with row click navigation.
- 503 handling on extract trigger.

### 7. Implement Extraction progress view with safe polling — DONE
Tasks:
- `setTimeout`-based polling with in-flight guard.
- Respects `retry_after`, defaults to 2000ms.
- Auto-navigates on completion, shows error on failure.
- Always stops polling on view exit.

### 8. Implement Extraction detail view — DONE
Tasks:
- Exam info header, findings with presence/location/attribute badges.
- Non-finding text, validation warnings/errors, model info.
- Response flattening: `{ ...detail, ...detail.extraction }`.

### 9. Implement MVP correction form (comment only) — DONE
Tasks:
- Comment textarea (required) and created_by input (optional).
- Refreshes corrections list after successful submit.

### 10. Static serving (Caddy reverse proxy) — DONE
Static files in `extractor-ui/` are served by Caddy via Docker Compose. The `Caddyfile` at the repo root:
- Serves `extractor-ui/` at `/`
- Proxies `/api/*` to the FastAPI backend
- Accessible at `http://localhost:8080` after `docker compose up`

## Outstanding Issues

1. **Structured correction forms**: Only comment corrections are supported. `add_finding` and `update_finding` forms are post-MVP.
2. ~~**Real backend integration testing**~~: DONE — `tests/test_integration.py` runs Playwright E2E tests against the full Docker Compose stack (Caddy → FastAPI → TaskIQ → Redis) with real LLM extraction. Run with `uv run pytest -m integration -v`. Tests auto-start Docker Compose if needed.
3. **Duplicate report UX**: The API returns `seen_before` when a duplicate report is submitted; the UI does not yet surface this to the user.
4. **Pagination lacks total count**: The API does not return a total count, so the UI cannot show "page X of Y".

## MVP Verification Checklist
1. Start full stack: `docker compose up -d --build --wait`.
2. Open the UI at `http://localhost:8080`.
3. Submit a report and confirm returned ID.
4. Submit and extract from submit page.
5. Watch extracting page transition to extraction detail automatically.
6. Open reports list, paginate, and open a report detail.
7. Trigger extraction from report detail and confirm progress flow.
8. Add a comment correction and verify it appears in the list.
9. Hard refresh on `#/reports/{id}` and `#/extractions/{id}` and confirm both still load.
10. Force error states:
   - empty report submit
   - nonexistent report id route
   - nonexistent extraction id route
   - extraction trigger enqueue failure (`503`) shows retryable message and no route change
11. Toggle dark mode and refresh to verify persistence.

## Expected Post-MVP Iteration Areas
These are likely next issues, but exact priority should be decided after MVP usage feedback.

1. Structured correction forms:
- Add `add_finding` and `update_finding` UI.
- Ensure payloads include required fields like `proposed_finding.report_text` and `target_finding_index`/`target_json_path`.

2. Pagination UX upgrades:
- Add total count, direct page jumps, and URL-preserved page state if needed.

3. Polling refinements:
- Better retry/backoff behavior for intermittent failures.
- Optional background polling resume if user revisits extracting route.

4. Better duplicate-report flow:
- Improve UX around `seen_before` (show prior extractions, suggest rerun vs reuse).

5. ~~Test coverage:~~ DONE
- ~~Add lightweight browser automation for route loading, polling transitions, and correction submission.~~
- 48 Playwright E2E tests added in `tests/test_ui.py`, covering all views and flows.

## Related Documentation
- [`docs/frontend-usage.md`](../frontend-usage.md) — User guide with screenshots
- [`docs/frontend-internals.md`](../frontend-internals.md) — Developer/agent reference for implementation details
