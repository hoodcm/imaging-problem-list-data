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
Lines 1-34:    Mock data (users, report with patient_id, job, extraction) and USE_MOCK flag
Lines 36-61:   mockApiFetch() — URL-parameter-driven mock API with users endpoint
Lines 63-???:  extractorApp() — single Alpine.js component
  State:       submitForm includes patientId field
               users[], usersLoading, usersError for user dropdown
               correctionForm.username pre-populated from users API
  Router:      (navigateFromHash, navigate)
  API client:  apiFetch
  Submit:      submitReport + submitAndExtract send patient_id to API
  Reports:     loadReports, loadReport
  Extraction:  triggerExtraction
  Polling:     startPolling, pollJob, stopPolling
  Detail:      loadExtraction calls loadUsers() to populate dropdown
               loadCorrections
  Corrections: submitCorrection and submitFindingEdit gated by users availability
               UI renders `author` with `created_by` fallback
  Utilities:   formatDate, truncateId, toggleDarkMode
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

The mock API (`mockApiFetch()`, lines 36-61) includes URL pattern matching for:
- `GET /users` — returns list of mock users
- `POST /reports` — accepts patient_id field
- `POST /corrections` — accepts `username` and returns structured author object (supports all correction types including `update_finding`)

Mock corrections include:
```javascript
{
  id: 'mock-correction-1',
  author: { username: 'talkasab', name: 'Tarik Alkasab', email: 'tarik@alkasab.org' },
  created_by: null,  // legacy fallback not used for new corrections
  created_at: new Date().toISOString()
}
```

The mock data shape matches the real API's response structures.

### Response Flattening

The extraction detail API response nests `exam_info`, `findings`, and `non_finding_text` under an `extraction` sub-object. The `loadExtraction()` method flattens this:

```javascript
this.currentExtraction = { ...detail, ...detail.extraction };
```

This allows templates to access `currentExtraction.exam_info` directly rather than `currentExtraction.extraction.exam_info`.

### Extraction Request Construction

`buildExtractBody(opts)` constructs the extract request body, only including fields that have non-empty values:

```javascript
buildExtractBody(opts) {
    const body = {};
    if (opts.examDescription?.trim()) body.study_description = opts.examDescription.trim();
    if (opts.model?.trim()) body.model = opts.model.trim();
    if (opts.reasoning?.trim()) body.reasoning = opts.reasoning.trim();
    return body;
}
```

This is shared between `submitAndExtract()` (submit view) and `triggerExtraction()` (report detail view).

### Finding-Level Edit State

Per-finding inline editing uses two Alpine.js reactive objects keyed by finding index (`fIdx`):

```javascript
findingEditState: {},      // { [fIdx]: true/false } — tracks which finding is being edited
findingEditForms: {},      // { [fIdx]: { presence, location_*, attributes_json, comment } }
```

**Methods:**
- `startFindingEdit(fIdx, finding)`: Opens edit form for finding at index `fIdx`, prefills form with current finding values. Converts attributes array to JSON object string.
- `cancelFindingEdit(fIdx)`: Closes edit form without submitting.
- `submitFindingEdit(fIdx)`: Validates attributes JSON, constructs complete `ExtractedFinding` as `proposed_finding`, submits `update_finding` correction to API, closes form, reloads corrections list.

The inline edit form uses Alpine's `:id` and `:for` attribute bindings to create unique IDs per finding (e.g., `presence-0`, `location-region-0`) for proper label/input association and Playwright test accessibility.

**Payload structure for `update_finding`:**
```javascript
{
  correction_type: 'update_finding',
  target_finding_index: fIdx,
  proposed_finding: {
    finding_name: 'kidney stone',              // Preserved from original
    presence: 'absent',                        // Edited value
    location: {
      body_region: 'abdomen',
      specific_anatomy: 'right kidney',        // Edited value
      laterality: 'right'
    },
    attributes: [                              // Converted from JSON textarea
      { key: 'size', value: '5mm' }
    ],
    report_text: '3mm left kidney stone.'     // Preserved verbatim quote
  },
  comment: 'Corrected presence and location',
  username: 'talkasab'
}
```

**Note:** The `proposed_finding` field contains a complete `ExtractedFinding` object matching the backend's expected structure. This ensures API contract compliance (backend requires proper structured finding, not nested objects in `attribute_overrides`).

### User Loading and Selection

When entering extraction detail view, `loadExtraction()` calls `loadUsers()` to populate the username dropdown for corrections:

```javascript
async loadUsers() {
  try {
    this.usersLoading = true;
    this.usersError = null;
    this.users = await this.apiFetch('/users');
    // Default selection: prefer 'talkasab', else first user
    const defaultUser = this.users.find((u) => u.username === 'talkasab') || this.users[0];
    this.correctionForm.username = defaultUser ? defaultUser.username : '';
  } catch (e) {
    this.usersError = e.message || 'Failed to load users';
    this.users = [];
    this.correctionForm.username = '';
  } finally {
    this.usersLoading = false;
  }
}
```

**Correction submission gating:**
- Both `submitCorrection()` (global comments) and `submitFindingEdit()` (finding-level edits) validate that `correctionForm.username` is non-empty
- UI disables submit buttons when:
  - `usersLoading` is true
  - `usersError` is set
  - `users.length === 0`
  - `correctionForm.username.trim()` is empty
- Error/empty state is shown inline in the UI to explain why submission is unavailable
- No fallback to free-text username input (confirmed behavioral decision in Stage 4 planning)


### Polling

Job polling uses `setTimeout` (not `setInterval`) with an in-flight guard (`pollInFlight`) to prevent overlapping requests. The poll respects `retry_after` from the server response, defaulting to 2 seconds. Polling always stops on navigation away via `stopPolling()` called in `navigate()`.

### Dark Mode

Two-part implementation:
1. **Flash prevention**: `<head>` script (before render) reads `localStorage` and sets `dark` class on `<html>`.
2. **Runtime toggle**: Alpine.js `isDark` state and `toggleDarkMode()` method update the class and localStorage.

## Testing

58 Playwright E2E tests in `tests/test_ui.py`. Run with:

```bash
uv run pytest tests/test_ui.py -v
```

Tests use mock mode, so no backend is needed. A module-scoped fixture starts a Python HTTP server on port 8787.

**Test classes:**
- `TestDarkMode` — toggle and persistence
- `TestSubmitView` — report submission and input validation
- `TestReportsList` — pagination, filtering, empty state
- `TestReportDetail` — metadata, extractions list, trigger extraction
- `TestExtractionDetail` — findings, validation, metadata, corrections list
- `TestCorrections` — correction form, username dropdown, submit button states
- `TestUserDropdown` — user loading, default selection, submit gating
- `TestFindingEdit` — inline edit form, prefill, save/cancel actions
- `TestFullFlow` — end-to-end submission and navigation paths

Test classes:
- `TestPageShell` — page load, nav links, routing, console errors
- `TestDarkMode` — toggle behavior, persistence across reload
- `TestSubmitView` — form fields, validation, submit, submit & extract
- `TestReportsList` — table columns, pagination, refresh, row navigation
- `TestReportDetail` — deep link, metadata, extraction trigger, back navigation
- `TestExtractionDetail` — exam info, findings, presence/location badges, attributes, model info
- `TestCorrections` — form presence, disabled state, submit and clear
- `TestFindingEdit` — inline edit button, form open/close, prefill, cancel, submit
- `TestFullFlow` — end-to-end journeys through multiple views

## API Alignment Notes

The frontend is validated against the OpenAPI spec from the running backend. Key alignment decisions:

- **Extraction detail response**: API nests extraction data under `extraction` sub-object. Frontend flattens it on load.
- **`reasoning_effort`**: API returns a string (e.g., `"low"`, `"medium"`), not a boolean. UI displays it as-is.
- **`FindingAttribute`**: Uses `key`/`value` fields (not `name`/`value`).
- **503 handling**: Extract endpoints may return 503 when the extraction service is unavailable. The UI shows an error banner and does not navigate.

## Post-MVP Work

See `docs/archive/extractor-frontend.md` § "Expected Post-MVP Iteration Areas" for historical improvement plans including structured correction forms, pagination upgrades, and polling refinements.
