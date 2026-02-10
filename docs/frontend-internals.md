# Extraction Frontend Internals

Developer and agent reference for the extraction frontend implementation.

## Architecture

The frontend is a zero-build static SPA using:
- **Alpine.js 3.x** for reactive state and view switching
- **Tailwind CSS v4** via CDN (`@tailwindcss/browser@4`)
- **Flowbite 4.0.1** via CDN for UI components

All code lives in two files:
- `extractor-ui/index.html` (~796 lines) — markup, views, and CDN imports
- `extractor-ui/app.js` (~377 lines) — single Alpine component with all state and logic

## File Organization

### `app.js` Structure

```
Lines 1-21:    Mock data and USE_MOCK flag
Lines 23-40:   mockApiFetch() — URL-parameter-driven mock API
Lines 42-376:  extractorApp() — single Alpine.js component
  State:       lines 44-72
  Router:      lines 74-133  (init, navigateFromHash, navigate)
  API client:  lines 135-152 (apiFetch)
  Submit:      lines 154-227 (submitReport, buildExtractBody, submitAndExtract)
  Reports:     lines 229-250 (loadReports, loadReport)
  Extraction:  lines 252-271 (triggerExtraction)
  Polling:     lines 273-308 (startPolling, pollJob, stopPolling)
  Detail:      lines 310-330 (loadExtraction, loadCorrections)
  Corrections: lines 332-355 (submitCorrection)
  Utilities:   lines 357-374 (formatDate, truncateId, toggleDarkMode)
```

### `index.html` Structure

```
Lines 1-64:    <head> — CDN imports, dark mode init script, x-cloak style
Lines 65-111:  Header — nav links, dark mode toggle button
Lines 113-136: Global error banner (Alpine x-show, dismissible)
Lines 139-244: Submit view — form fields, action buttons, success message
Lines 246-332: Reports list — table, empty state, pagination
Lines 334-464: Report detail — metadata, report text, run extraction, extractions table
Lines 466-532: Extracting view — spinner, status badge, failure message
Lines 534-782: Extraction detail — exam info, findings, non-finding text,
               validation, model info, corrections list, correction form
Lines 788-795: Footer scripts — Flowbite JS, app.js
```

## Key Patterns

### Routing

Hash-based routing via `window.location.hash`. The `navigateFromHash()` method parses the hash with regex patterns and dispatches to `navigate(view, params)`. Order matters — the extracting route (`/reports/{id}/extracting/{job_id}`) must match before the report detail route (`/reports/{id}`).

Routes:
| Hash | View | Data loaded |
|---|---|---|
| `#/` | `submit` | (none) |
| `#/reports` | `reports` | `loadReports()` |
| `#/reports/{id}` | `reportDetail` | `loadReport(id)` |
| `#/reports/{id}/extracting/{job_id}` | `extracting` | `startPolling(job_id, id)` |
| `#/extractions/{id}` | `extractionDetail` | `loadExtraction(id)` |

Unknown routes redirect to `#/`.

### API Client

`apiFetch(path, options)` wraps `fetch()` with:
- Automatic `/api` prefix (e.g., path `/reports` → `GET /api/reports`)
- JSON content-type header
- Error extraction from response body (`.detail` field from FastAPI)
- Status code preserved on thrown error objects for `503` handling

When `?mock` is in the URL, `apiFetch` delegates to `mockApiFetch()` instead.

### Mock Layer

The mock API (`mockApiFetch()`, lines 23-40) is ~18 lines of URL pattern matching that returns static data from `MOCK_DATA`. It introduces a 50ms delay to simulate async. The mock data shape matches the real API's `ExtractionDetailResponse` structure, including the nested `extraction` sub-object.

### Response Flattening

The API's `ExtractionDetailResponse` nests `exam_info`, `findings`, and `non_finding_text` under an `extraction` sub-object. The `loadExtraction()` method flattens this:

```javascript
this.currentExtraction = { ...detail, ...detail.extraction };
```

This allows templates to access `currentExtraction.exam_info` directly rather than `currentExtraction.extraction.exam_info`.

### Extraction Request Construction

`buildExtractBody(opts)` constructs the extract request body, only including fields that have non-empty values:

```javascript
buildExtractBody(opts) {
    const body = {};
    if (opts.examDescription?.trim()) body.exam_description = opts.examDescription.trim();
    if (opts.model?.trim()) body.model = opts.model.trim();
    if (opts.reasoning?.trim()) body.reasoning = opts.reasoning.trim();
    return body;
}
```

This is shared between `submitAndExtract()` (submit view) and `triggerExtraction()` (report detail view).

### Polling

Job polling uses `setTimeout` (not `setInterval`) with an in-flight guard (`pollInFlight`) to prevent overlapping requests. The poll respects `retry_after` from the server response, defaulting to 2 seconds. Polling always stops on navigation away via `stopPolling()` called in `navigate()`.

### Dark Mode

Two-part implementation:
1. **Flash prevention**: `<head>` script (before render) reads `localStorage` and sets `dark` class on `<html>`.
2. **Runtime toggle**: Alpine.js `isDark` state and `toggleDarkMode()` method update the class and localStorage.

## Testing

48 Playwright E2E tests in `tests/test_ui.py`. Run with:

```bash
uv run pytest tests/test_ui.py -v
```

Tests use mock mode, so no backend is needed. A module-scoped fixture starts a Python HTTP server on port 8787.

Test classes:
- `TestPageShell` — page load, nav links, routing, console errors
- `TestDarkMode` — toggle behavior, persistence across reload
- `TestSubmitView` — form fields, validation, submit, submit & extract
- `TestReportsList` — table columns, pagination, refresh, row navigation
- `TestReportDetail` — deep link, metadata, extraction trigger, back navigation
- `TestExtractionDetail` — exam info, findings, presence/location badges, attributes, model info
- `TestCorrections` — form presence, disabled state, submit and clear
- `TestFullFlow` — end-to-end journeys through multiple views

## API Alignment Notes

The frontend is validated against the OpenAPI spec from the running backend. Key alignment decisions:

- **ExtractionDetailResponse**: API nests extraction data under `extraction` sub-object. Frontend flattens it on load.
- **`reasoning_effort`**: API returns a string (e.g., `"low"`, `"medium"`), not a boolean. UI displays it as-is.
- **`FindingAttribute`**: Uses `key`/`value` fields (not `name`/`value`).
- **503 handling**: Extract endpoints may return 503 when the extraction service is unavailable. The UI shows an error banner and does not navigate.

## Post-MVP Work

See `docs/extractor-frontend.md` § "Expected Post-MVP Iteration Areas" for planned improvements including structured correction forms, pagination upgrades, and polling refinements.
