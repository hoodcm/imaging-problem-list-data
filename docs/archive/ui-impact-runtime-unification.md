# UI Impact Notes — Runtime Unification (Backend Facts Only)

Date: 2026-02-16

This document captures backend contract/runtime behavior changes introduced by the extraction runtime unification work. It is intended as factual input for later UI planning and implementation.

## 1) Single runtime path now drives all extraction surfaces

- Worker/API jobs, CLI, batch CLI, and eval now run through the same orchestrated runtime path.
- There is no separate legacy direct-agent execution path in core extraction runtime flow.

## 2) Status message behavior is canonical-stage-first

- Runtime status messages are emitted in canonical format:
  - `[stage:<stage>] <detail>`
- Terminal status messages are canonical as well:
  - completed: `[stage:completed] extraction_complete`
  - completed with warnings: `[stage:completed_with_warnings] extraction_complete`
  - failed: `[stage:failed] <public_error_code>`
- Legacy terminal strings such as:
  - `Starting extraction`
  - `Extraction complete`
  - `Extraction failed`
  are no longer the source of truth for backend status updates.

## 3) Stage vocabulary now reflects orchestrator lifecycle

Observed stage keys used by runtime/orchestrator:

- `preflight`
- `sectionize`
- `extract_sections`
- `repair_failed_sections`
- `merge_dedupe`
- `validator_review`
- `validate_output`
- `apply_coding`
- `persist`
- `completed`
- `completed_with_warnings`
- `failed`

Observed detail patterns include structured tokens such as:

- `unit=<label> attempt=<n> status=<phase>`
- `start units=<n> max_concurrency=<n>`
- `summary ...`
- `remaining_failed_units=<n> labels=... errors=...`

## 4) Job polling payload expectations

For canonical stage status strings, `GET /api/jobs/{job_id}` currently returns:

- `status_message`: canonical stage string
- `status_event`: parsed structured object when `status_message` is stage-formatted:
  - `version`
  - `stage`
  - `detail`

Example terminal payload (completed):

- `status_message`: `[stage:completed] extraction_complete`
- `status_event`: `{\"version\":\"v2\",\"stage\":\"completed\",\"detail\":\"extraction_complete\"}`

## 5) Runtime semantics changed for CLI/batch/eval

- CLI/batch/eval now emit/observe orchestrator stage progression, not only direct-agent progress strings.
- Output extraction semantics now match worker orchestration behavior (section/chunk/repair/merge flow), rather than a separate direct-agent path.

## 6) Compatibility assumptions

- Backend intentionally removed compatibility-focused orchestration branches/knobs in this pass.
- Any UI logic relying on legacy status-message text should be considered stale and updated to canonical stage/event behavior.
