# Implementation Plan: patient linkage, user-attributed corrections, and finding-level edit UX

## Current Status (2026-02-12)

**✅ Complete:** Stages 0, 1, 2, 3, 4 (backend foundation + API contracts + finding-level edit UX + user dropdown selector)  
**🎉 All Stages Complete!**  
**📊 Test Status:** 258 unit tests pass, 58 UI tests pass (+4 from Stage 3 baseline)  
**💾 Migration:** 17d9bf28412d applied (users, patient_id, correction author FK)  
**📝 Commits:** *(pending: Stage 4 implementation)*

## Problem statement and approach
We need to improve the extractor workflow across backend + frontend in three connected areas:
1. Associate reports to the same patient.
2. Record corrections against an identified user (username/name/email).
3. Improve extraction readability and allow correction inline per finding (edit-in-place style).

Approach: ship this in additive, migration-safe stages using Alembic + SQLModel updates, API contract evolution, then Alpine/Flowbite UI updates, with tests at each stage.

## Confirmed decisions (from clarification)
- Finding-level correction scope (phase 1): **inline edit existing extracted findings only** via `update_finding`.
- Editable fields per finding: **moderate** — presence status, location, attributes, and a comment. Not finding_name or report_text quote.
- Report/patient linkage (phase 1): **optional `patient_id` string** on reports.
  - Source: **manual text input** on the report submission form now; agent extraction from report text is future work.
- Deduping behavior (phase 1): **keep existing global text-hash dedupe** unchanged.
- Correction author model: **must be an identified user from a users table**; no user-creation UI yet.
- Pre-auth user selection in UI: **dropdown selector from API users**, default to `talkasab`.
- Seed/base user to include: `talkasab` / `Tarik Alkasab` / `tarik@alkasab.org`.
- Global comment box: **keep** — serves as extraction-level commentary. Most corrections will be per-finding, but the global comment box stays for overall feedback.
- Legacy `created_by` display: **show as-is with a visual hint** (e.g., italic + "unlinked" badge) when the value doesn't match a known user.

## Staged execution plan

### Stage 0 — Baseline safety checks ✅
- [x] Run baseline tests before code changes:
  - `task test` (runs `test:unit` internally) — 251 passed
  - `uv run pytest tests/test_ui.py -v` — 48 passed
- [x] Record any pre-existing failures so new regressions are isolated — no pre-existing failures

### Stage 1 — Database and domain model foundation (Alembic-first) ✅
- [x] Update SQLModel schema in `src/finding_extractor/store.py`:
  - [x] Add `users` table (`username`, `name`, `email`, `created_at`).
  - [x] Add nullable `patient_id` column to `reports`.
  - [x] Add correction author linkage to `corrections` (username-based reference to users).
- [x] Keep migration safety per `docs/schema-migrations.md`:
  - [x] Create migration: `task db:revision MSG="add users patient-id correction-author"` — 17d9bf28412d
  - [x] Review generated revision for nullable/additive changes and SQLite batch alter.
  - [x] Apply/check: `task db:migrate`, `task db:heads`, `task db:current`, `task db:check`.
  - [x] Update `ExtractionStore.EXPECTED_REVISION` to new head.
- [x] Seed default user record for `talkasab` via migration.
- [x] Add store methods: `create_user()`, `get_user()`, `list_users()`.
- [x] Update `upsert_report()` to accept optional `patient_id`.
- [x] Update `record_correction()` to accept optional `username`.
- [x] Backend tests updated (`tests/test_store.py`, `tests/test_migrations.py`).
- [x] Documentation updated (`docs/persistence-usage.md`, `docs/persistence-internals.md`).
- [x] Verification: 253 unit tests pass, 48 UI tests pass.

### Stage 2 — Store + API contract updates ✅
- [x] Extend report API contracts (`api_models.py`, `api_routes.py`, store dataclasses/mappers):
  - [x] `POST /api/reports` accepts optional `patient_id`.
  - [x] Report submission form in `extractor-ui/` gets an optional "Patient ID" text input.
  - [x] `GET /api/reports` and `GET /api/reports/{id}` return `patient_id`.
- [x] Extend correction author contracts:
  - [x] Replace free-text correction author input contract with required user identity reference.
  - [x] Return structured author object on correction responses (`username`, `name`, `email`).
  - [x] For legacy corrections where `created_by` doesn't match a user, return the raw string in a fallback field.
- [x] Add users endpoint for UI selector:
  - [x] `GET /api/users` returns user list; include deterministic ordering.
- [x] Add mock handlers for new endpoints/fields in `extractor-ui/app.js` mock layer:
  - [x] Mock `GET /api/users` response.
  - [x] Mock `patient_id` in report responses.
  - [x] Mock structured author in correction responses.
- [x] Preserve PHI-safe logging conventions (`docs/logging-usage.md`):
  - [x] Log IDs/usernames/status only; do **not** log report text or verbatim finding quotes.
  - [x] Use structured logging fields at API/service callsites.

Stage 2 closure notes:
- [x] Post-implementation consistency fix applied: extractor UI correction submit now sends `username`, correction display renders `author` with `created_by` fallback, and both report submit paths include `patient_id`.
- [x] Backend tests updated with 4 new tests (`tests/test_api.py`).
- [x] UI tests updated with Patient ID assertions and username field checks (`tests/test_ui.py`).
- [x] Documentation synced (`docs/api-usage.md`, `docs/frontend-usage.md`, `docs/frontend-internals.md`, `docs/DEV_LOG.md`).
- [x] Verification: 257 unit tests pass, 49 UI tests pass (+1 new test).

### Stage 3 — Extraction detail UX and finding-level edit plumbing ✅
- [x] Improve finding presentation in `extractor-ui/index.html` for clearer per-finding structure (name/presence/location/attributes/quote blocks with explicit labels).
- [x] Implement per-finding inline correction controls in Alpine (`extractor-ui/app.js`):
  - [x] Add per-finding edit state keyed by finding index.
  - [x] Editable fields: **presence status, location, attributes, and comment**.
  - [x] Prefill edit form from selected finding.
  - [x] Submit `update_finding` correction with `target_finding_index`.
  - [x] Keep correction action colocated with the finding card.
- [x] Keep global comment-only correction box for extraction-level commentary (existing behavior preserved).
- [x] Add mock handler support for `update_finding` correction submissions (generic mock already supported).
- [x] Keep UI implementation aligned with stack rules:
  - [x] Alpine state/methods inside `extractorApp()`.
  - [x] Flowbite/Tailwind component patterns from current CDN setup.
  - [x] No imperative DOM-query-driven behavior.

**Stage 3 kickoff checklist (execute in order):**
- [x] Reconfirm green baseline before edits:
  - [x] `task test` — 257 passed
  - [x] `uv run pytest tests/test_ui.py -v` (Playwright) — 49 passed
- [x] Implement Stage 3 UI changes in small slices (`index.html` presentation first, then `app.js` inline edit plumbing, then mock updates).
- [x] Add/adjust Playwright coverage in `tests/test_ui.py` for finding-level edit open/edit/submit behavior in mock mode.
- [x] Update all relevant docs for Stage 3 completion:
  - [x] `docs/frontend-usage.md`
  - [x] `docs/frontend-internals.md`
  - [x] `docs/improving-ui-plan.md` (check off completed Stage 3 items)
  - [x] `docs/DEV_LOG.md`
- [x] Final green gate (required before declaring Stage 3 done):
  - [x] `task lint` (Python passed, eslint unavailable)
  - [x] `task test` — 257 passed
  - [x] `uv run pytest tests/test_ui.py -v` (Playwright) — 54 passed (+5 new tests)

**Stage 3 contract alignment fix (2026-02-12):**
- [x] Fixed `submitFindingEdit()` to use `proposed_finding` (complete ExtractedFinding structure) instead of malformed nested `attribute_overrides`.
- [x] Added backend test `test_update_finding_with_proposed_finding()` to guard against this contract drift.
- [x] Updated `docs/frontend-internals.md` with corrected payload example showing proper `proposed_finding` structure.
- [x] Verified all tests green: 258 unit tests (+1 new test for contract validation), 54 UI tests (unchanged).
- [x] **Stage 3 confirmed merge-ready** ✅

### Stage 4 — User selection UX (pre-auth) ✅
- [x] Replace correction username text input with Flowbite select/dropdown backed by `GET /api/users`.
- [x] Keep both correction submit paths wired to selected user:
  - [x] Global comment-only submit (`submitCorrection`)
  - [x] Finding-level edit submit (`submitFindingEdit`)
- [x] Load users when entering extraction detail (cache in component state for reuse while app is open).
- [x] Default selection behavior:
  - [x] Choose `talkasab` when present.
  - [x] Else choose first returned user.
- [x] Empty/error behavior (confirmed decision):
  - [x] If users load fails or returns empty list, disable correction submit actions.
  - [x] Show explicit inline error state in correction area (no silent fallback).
  - [x] Do **not** fallback to free-text username input.
- [x] Preserve existing correction rendering:
  - [x] Continue showing structured `author` when available.
  - [x] Continue legacy fallback for `created_by` rows with italic + "unlinked" badge.

**Stage 4 kickoff checklist (execute in order):**
- [x] Reconfirm green baseline before edits:
  - [x] `task lint`
  - [x] `task test`
  - [x] `uv run pytest tests/test_ui.py -v` (Playwright)
- [x] Implement UI state updates in `extractor-ui/app.js`:
  - [x] Add users loading/error state and selected username wiring.
  - [x] Ensure correction actions are disabled when users are unavailable.
  - [x] Keep Alpine-only state/method pattern (no imperative DOM logic).
- [x] Implement UI markup updates in `extractor-ui/index.html`:
  - [x] Replace username text input with Flowbite select.
  - [x] Add explicit loading/empty/error help text near selector.
  - [x] Keep existing accessibility label coverage used by Playwright.
- [x] Mock mode parity:
  - [x] Keep mock `GET /api/users` support aligned with production shape.
  - [x] Mock already included `/users` endpoint with talkasab user.
- [x] Final verification gate (required):
  - [x] `task lint` — passed
  - [x] `task test` — 258 passed
  - [x] `uv run pytest tests/test_ui.py -v` — 58 passed (+4 new tests for user dropdown)
  - [x] Runtime smoke test — users endpoint working, dropdown functional
- [x] Documentation updates:
  - [x] `docs/frontend-usage.md` — updated correction section with dropdown behavior and error states
  - [x] `docs/frontend-internals.md` — added User Loading and Selection section, updated test classes
  - [x] `docs/improving-ui-plan.md` — marked Stage 4 complete with test counts
  - [x] `docs/DEV_LOG.md` — (next step)

**Note:** Stage 2 implemented text input for username (functional requirement). Stage 4 upgrades to dropdown selector (UX improvement).

### Stage 5 — Tests and verification (ongoing with each stage)

**Completed in Stages 0-2:**
- [x] Backend/store/API tests:
  - [x] Update `tests/test_store.py` for new schema/author rules/patient_id roundtrip.
  - [x] Update `tests/test_api.py` for report patient_id, users endpoint, structured correction author, and validation failures.
  - [x] Update `tests/test_migrations.py` for new head revision and table/column expectations.
- [x] UI tests (`tests/test_ui.py`):
  - [x] Add checks for patient field visibility and metadata display.
  - [x] Add check for username required field behavior.
- [x] Full validation commands (Stages 0-2):
  - [x] `task lint` — passes
  - [x] `task test` — 257 passed
  - [x] `uv run pytest tests/test_ui.py -v` — 49 passed

**Completed in Stage 3 (finding-level edits):**
- [x] UI tests: Added 5 new tests for finding-level inline edit UI and submit flow (`TestFindingEdit` class).
- [x] Full validation:
  - [x] `task lint` — Python passed (eslint unavailable)
  - [x] `task test` — 257 passed
  - [x] `uv run pytest tests/test_ui.py -v` — 54 passed

**Remaining for Stage 4 (user dropdown):**
- [x] UI tests (`tests/test_ui.py`) for dropdown behavior:
  - [x] Selector is visible and populated from users API in mock mode.
  - [x] Default selection prefers `talkasab`.
  - [x] Correction submit controls respect enabled/disabled gating based on user availability.
  - [x] Finding-level edit submit respects same disabled/error gating.
  - [x] Existing correction and finding-edit happy-path tests remain green.
  - [x] Added 4 new tests in `TestUserDropdown` class
- [x] No backend API test changes needed (existing tests cover users endpoint)

**Final verification before merging feature branch:**
- [x] `task lint` — passed
- [x] `task test` — 258 passed
- [x] `uv run pytest tests/test_ui.py -v` — 58 passed (+4 new)
- [x] `task stack:up:full` and quick smoke of correction submission flow — users dropdown working
- [x] Stage 4 confirmed complete ✅

### Stage 6 — Documentation updates (ongoing with each stage)

**Completed in Stages 1-2:**
- [x] Update API docs (`docs/api-usage.md`) for:
  - [x] report `patient_id`
  - [x] users endpoint
  - [x] structured correction-author payloads
- [x] Update persistence docs (`docs/persistence-usage.md` / `docs/persistence-internals.md`) for new tables/relationships.
- [x] Update frontend docs (`docs/frontend-usage.md`, `docs/frontend-internals.md`) for username field and patient_id.
- [x] Update `docs/DEV_LOG.md` with Stages 1-2 entries.

**Completed in Stage 3:**
- [x] Update frontend docs for finding-level edit workflow (`docs/frontend-usage.md`, `docs/frontend-internals.md`).
- [x] Update `docs/DEV_LOG.md` with Stage 3 entry.
- [x] Update `docs/improving-ui-plan.md` to mark Stage 3 complete.

**Completed in Stage 4:**
- [x] Update `docs/frontend-usage.md` for dropdown-based correction author flow and disabled states.
- [x] Update `docs/frontend-internals.md` for users-loading/error state and submit gating logic.
- [x] Update `docs/improving-ui-plan.md` with truthful Stage 4 completion status + final test counts.
- [x] Update `docs/DEV_LOG.md` with concise Stage 4 implementation + verification entry. *(next)*

## Notes
- Use additive schema evolution only (nullable additions, no destructive migration), per `docs/schema-migrations.md`. ✅ Applied in Stage 1.
- Keep extraction job/error behavior and public error-code contract unchanged. ✅ Preserved.
- Keep report dedupe semantics unchanged in this phase (global `text_hash`) as requested. ✅ Preserved.
- All new/modified API endpoints need corresponding mock handlers in `extractor-ui/app.js` to avoid breaking Playwright E2E tests (`tests/test_ui.py` with `?mock` mode). ✅ Applied in Stage 2.

## Implementation History
- **Commit f094207**: Updated improving-ui-plan.md with resolved decisions
- **Commit 4bcda12**: Stage 1 schema changes + migration 17d9bf28412d
- **Commit 18111c4**: Stage 1 test updates (2 new tests)
- **Commit 34867fd**: Stage 1 documentation updates
- **Commit 4030cf5**: Stage 2 API contract updates
- **Commit d982b69**: Stage 2 documentation updates
- **Commit f79185a**: Stage 2 closure fixups (frontend/docs alignment)
