# Prompt For Follow-On Agent: UI Improvement Fixes

You are working in worktree `../imaging-problem-list-ui` on branch `feature/ui-iteration`.

## Goal
Resolve the confirmed UI/backend issues from code review so this branch is safe to merge into `dev`.

## Important Decision Already Made
Breaking `created_by` compatibility is acceptable for this release.
- Do **not** add backward-compat support for `created_by` payloads.
- Keep `username` as required for correction creation.
- Treat `created_by` as **removed** (not deprecated) in all updated docs and inline API comments.

## Issues To Fix

### 1) Remove Alpine runtime warnings in finding edit UI
Current problem:
- The inline edit form uses `x-show` with `x-model="findingEditForms[fIdx].*"`.
- Alpine evaluates bindings even when hidden, so before edit is opened it logs warnings like:
  - `Cannot read properties of undefined (reading 'presence')`

Relevant files:
- `extractor-ui/index.html`
- `extractor-ui/app.js`

Required outcome:
- No Alpine expression warnings on extraction detail load.
- No Alpine expression warnings after opening/canceling/saving finding edits.

Suggested implementation:
- Prefer rendering the edit form only when state exists (for example using `x-if`), or otherwise ensure all bindings are safe before evaluation.

### 2) Make finding edit payload always valid against backend schema
Current problem:
- UI allows arbitrary free-text for constrained enums (`body_region`, `laterality`).
- UI currently builds `location` object with `body_region: null` when field is blank, which fails backend validation for `ExtractedFinding.location`.

Relevant backend schema:
- `src/finding_extractor/models.py` (`FindingLocation`, `ExtractedFinding`)

Relevant UI files:
- `extractor-ui/index.html`
- `extractor-ui/app.js`

Required outcome:
- Finding edit submissions cannot generate invalid location payloads.
- If user clears location fields, payload should be valid (for example `location: null` when appropriate).
- Inputs for constrained fields should guide valid values (prefer selects for enum-like fields).

### 3) Eliminate N+1 user lookups when listing corrections
Current problem:
- `GET /api/extractions/{id}/corrections` maps each correction with an individual `get_user` call.

Relevant files:
- `src/finding_extractor/api_routes.py`
- `src/finding_extractor/api_models.py`
- `src/finding_extractor/store.py`

Required outcome:
- Avoid per-correction user query pattern for list endpoint.
- Keep response contract unchanged (`author` object + legacy `created_by` field in response).

## Testing Requirements
Add/adjust tests so regressions are caught:

1. UI tests (`tests/test_ui.py`)
- Add coverage that no console warnings/errors are emitted when visiting extraction detail and toggling finding edit UI in mock mode.
- Cover at least one path where location is cleared/edited and submission remains valid from UI perspective.

2. API/store tests
- Add or update tests to cover the non-N+1 corrections author mapping path.
- Keep existing correction response contract tests passing.

3. Run required checks
- `task lint`
- `task test`
- `uv run pytest tests/test_ui.py -v`

Also run a manual browser validation using Playwright tooling:
- Use `playwright-cli` skill if available.
- If `playwright-cli` binary is unavailable in shell, use Python Playwright (`uv run python ...`) and verify console is clean on extraction detail interactions.

## Documentation Requirements
- Update relevant docs to reflect the actual API contract change:
  - `created_by` request field is **removed**.
  - `username` is required for correction creation.
- Replace any lingering “deprecated” language for request payload usage with “removed.”
- Ensure examples in docs use `username` (and not `created_by`) for correction creation payloads.

## Implementation Constraints
- Follow `AGENTS.md` and existing repo patterns.
- Keep frontend stack Alpine + Flowbite + Tailwind CDN (no bundler/build-system introduction).
- Use `Taskfile.yml` commands for verification.
- Keep changes focused to these issues; avoid unrelated refactors.

## Deliverables
1. Code changes addressing all three issues.
2. Updated tests that fail before/fix after.
3. Brief summary including:
- What changed
- Why it fixes each issue
- Exact commands run and their results
- Any residual risks
