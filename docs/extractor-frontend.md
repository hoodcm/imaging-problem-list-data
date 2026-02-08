# Extraction Frontend Plan (MVP First)

## Goal
Build a lightweight static frontend for the extraction API using Alpine.js, with zero build step, that is simple enough for a junior engineer to implement directly.

This document is split into:
- MVP implementation steps (explicit, sequential, handoff-ready)
- Post-MVP expected issues (likely next work, but intentionally not over-specified)

## Stack and Constraints
- Alpine.js 3.x for state and view switching
- Tailwind CSS 3.x + Flowbite 4.0 via CDN
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

### 1. Bootstrap page shell (`index.html`)
Tasks:
- Include Tailwind CDN, Flowbite CSS/JS, Alpine CDN.
- Add dark-mode initialization script before render.
- Add `<div x-data="extractorApp()" x-init="init()">`.
- Add top navigation with links to `#/` and `#/reports`.
- Add global error banner component.
- Add `x-cloak` style.

Done when:
- Page loads with no JS errors.
- Alpine app initializes.
- Dark mode persists using localStorage.

### 2. Create base app state and router (`app.js`)
Tasks:
- Define single Alpine scope with state:
  - `currentView`
  - submit form fields and loading flags
  - report list data + pagination (`limit`, `offset`)
  - current report + extraction list
  - current job + poll timer token
  - current extraction + corrections
  - global `error`
- Implement `init()`, `navigate(hash)`, `navigateFromHash()`.
- On route change, clear stale async state and stop active polling timer.

Done when:
- Direct navigation to each hash route renders the expected empty/loading shell.
- Invalid hash route redirects to `#/`.

### 3. Add shared API helper
Tasks:
- Implement one helper for JSON requests (`apiFetch(path, options)`):
  - sets JSON headers
  - parses JSON response
  - throws readable errors for non-2xx
- Standardize all API calls through this helper.

Done when:
- A forced 404/500/503 shows a readable error in global banner.

### 4. Implement Submit view
Tasks:
- UI fields:
  - `reportText` (required textarea)
  - `sourceRef` (optional input)
  - `examDescription` (optional input)
- Buttons:
  - `Submit`: calls `POST /api/reports`, stores response, stays on submit view
  - `Submit & Extract`: submit report, then trigger extraction, then navigate to extracting route
- If `Submit & Extract` receives `503` from extract trigger, show retryable error and remain on submit view.
- Validate non-empty report text before request.

Done when:
- Submit returns a report id and displays confirmation.
- Submit & Extract navigates to `#/reports/{id}/extracting/{job_id}`.
- Submit & Extract handles `503` by showing error and not changing routes.

### 5. Implement Reports list view
Tasks:
- Call `GET /api/reports?limit={limit}&offset={offset}`.
- Render table with:
  - report id (truncated in UI)
  - source ref
  - created_at
- Row click navigates to `#/reports/{id}`.
- Add refresh button.
- Add simple prev/next controls:
  - prev disabled at offset 0
  - next disabled when returned rows < limit

Done when:
- Pagination works without duplicate/skip behavior.
- Refresh reloads data and keeps current page offset.

### 6. Implement Report detail view
Tasks:
- Load report from `GET /api/reports/{id}`.
- Load extraction summaries from `GET /api/reports/{id}/extractions`.
- Show report text and metadata.
- Add `Run Extraction` button that calls `POST /api/reports/{id}/extract` and navigates to extracting route.
- If `Run Extraction` receives `503`, show retryable error and keep user on report detail.
- Clicking extraction summary navigates to extraction detail route.

Done when:
- Deep link to `#/reports/{id}` works on hard refresh.
- Triggering extraction always creates one job and navigates to progress view.
- `Run Extraction` handles `503` without route changes.

### 7. Implement Extraction progress view with safe polling
Tasks:
- Route inputs: `report_id`, `job_id`.
- Poll `GET /api/jobs/{job_id}` with `setTimeout` loop (not `setInterval`).
- Prevent overlapping poll requests with an in-flight guard.
- Use `Retry-After` if provided, else default 2000 ms.
- On status:
  - `pending` / `running`: continue polling
  - `completed`: stop polling and navigate to `#/extractions/{extraction_id}`
  - `failed`: stop polling and show error with retry action
- Always stop polling when leaving extracting view.

Done when:
- Only one active poll loop exists at any time.
- No continued network polling after navigation away from extracting view.

### 8. Implement Extraction detail view
Tasks:
- Load extraction from `GET /api/extractions/{id}`.
- Render:
  - exam info header
  - findings list with presence badge, location, attributes, report text quote
  - non-finding text grouped by category
  - validation warnings/errors if present
  - model name/reasoning
- Load and show corrections list from `GET /api/extractions/{id}/corrections`.

Done when:
- Deep link to `#/extractions/{id}` renders full detail on hard refresh.

### 9. Implement MVP correction form (comment only)
Tasks:
- Add simple form on extraction detail:
  - comment textarea (required)
  - created_by input (optional)
- Submit sends `correction_type: "comment"` payload.
- Refresh corrections list after successful submit.

Done when:
- New comment appears immediately in corrections list after submit.

### 10. Wire static serving in FastAPI
Tasks:
- Mount static UI directory in API server.
- Ensure `/api/*` routes are registered before static root mount.

Reference:
```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="extractor-ui", html=True), name="ui")
```

Done when:
- `http://localhost:8001/` serves UI.
- `http://localhost:8001/api/reports` still reaches API (not static index).

## MVP Verification Checklist
1. Start backend: `uv run finding-extractor-api`.
2. Open `http://localhost:8001/`.
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

5. Test coverage:
- Add lightweight browser automation for route loading, polling transitions, and correction submission.
