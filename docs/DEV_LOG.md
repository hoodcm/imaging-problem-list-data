# Dev Log

## 2026-02-12 — Real OpenTelemetry span propagation test for API logging context

Added explicit API coverage that verifies trace/span log context is sourced from a real active OpenTelemetry span context (not a monkeypatched helper).

- `tests/test_api.py`
  - `test_request_context_middleware_binds_trace_and_span_when_available` now:
    - creates an OpenTelemetry `SpanContext` + `NonRecordingSpan`
    - activates it with `use_span(...)` around a real API request
    - asserts middleware-bound `trace_id` and `span_id` match the active span
- Logging behavior remains unchanged; this strengthens confidence in context propagation wiring.

## 2026-02-12 — Eval harness refinements: retries + Phase 1.5 pydantic-evals integration

Two focused improvements to the eval harness shipped in Phase 1:

### Per-case retries
- Added `eval_retries` setting to `config.py` (`IPL_EVAL_RETRIES`, default 1, range 0–5).
- Added `retries` field to `EvalRunConfig` dataclass.
- `_build_retry_config()` in `runner.py` builds a tenacity config dict (`stop_after_attempt` + `wait_exponential`) and passes it to `dataset.evaluate(retry_task=...)`.
- Added `--retries` CLI option to `eval_cli.py`.

### Deeper pydantic-evals integration
- **Bool assertions**: `VerbatimQuoteEvaluator.verbatim_pass` now returns `bool` via `EvaluationReason` → routes to `case.assertions` (not `case.scores`). `verbatim_rate` stays as float score.
- **EvaluationReason**: `FindingDetectionEvaluator.finding_f1` returns reason with match/FP/FN counts. `VerbatimQuoteEvaluator.verbatim_pass` returns reason with verbatim counts.
- **Shared tokenization**: `NonFindingClassificationEvaluator` now imports `tokenize()` and `jaccard_similarity()` from `matching.py` instead of inlining Jaccard calculation.
- **Assertion averages**: `_extract_averages()` in `runner.py` computes per-assertion pass rates from per-case data and merges them into the averages dict so threshold checking works uniformly.

### Code review revisions (same session)
- **Reverted `_match_or_default()` helper**: Originally added to consolidate matching boilerplate across 4 evaluators, but introduced a positional 3-tuple return and redundant None checks. Restored the clearer inline pattern (3 lines per evaluator).
- **Promoted tokenization to public API**: Renamed `_tokenize()` → `tokenize()` and `_jaccard_similarity()` → `jaccard_similarity()` in `matching.py` since they're now imported across module boundaries by `evaluators.py`.

### Files modified
- `src/finding_extractor/config.py` — `eval_retries` setting
- `src/finding_extractor/eval/models.py` — `retries` on `EvalRunConfig`
- `src/finding_extractor/eval/runner.py` — retry wiring, assertion averages
- `src/finding_extractor/eval/evaluators.py` — bool assertions, EvaluationReason, shared helper, tokenization reuse
- `src/finding_extractor/eval_cli.py` — `--retries` option
- `config.toml.example` — `eval_retries`
- `docs/configuration.md`, `docs/eval-usage.md`, `docs/eval-internals.md` — updated tables and design notes
- `docs/extractor-agent-plan.md` — marked retries + Phase 1.5 completed
- `tests/test_eval_evaluators.py` — updated for bool assertions, EvaluationReason
- `tests/test_eval_cli.py` — `--retries` option tests

**Verification:** `task lint` clean, `task test:unit` passed.

## 2026-02-12 — Logging plan Stage 3 implemented (request/task context + structured callsites)

Completed Stage 3 execution checklist from `docs/logging-plan.md` with minimal, PHI-safe changes.

- `src/finding_extractor/api.py`
  - Added API request middleware binding `request_id`, `http_method`, `http_path`.
  - Added best-effort OpenTelemetry context binding (`trace_id`, `span_id`) when an active valid span exists; silent no-op when absent.
  - Added context cleanup (`clear_contextvars`) at request end.
  - Converted readiness/lifecycle/request logs to structured key/value style.
- `src/finding_extractor/tasks.py`
  - Added per-task context binding (`clear_contextvars` + `job_id`/`report_id`) with cleanup at task end.
  - Converted high-value task lifecycle/error/status logs to structured key/value style.
- `src/finding_extractor/api_services.py`
  - Converted enqueue lifecycle/error logs to structured key/value style.
- Added coverage:
  - `tests/test_api.py`: request context keys and optional trace/span context binding behavior.
  - `tests/test_tasks.py`: worker log context includes `job_id` and `report_id` and is cleared after run.
## 2026-02-12 — Fix batch status watch double-read bug

The `status --watch` loop in `batch_cli.py` read state twice per iteration — once inside `print_once()` to display, and again after to check for terminal status. When the run transitioned to a terminal state between iterations, the loop exited without ever printing the final state.

- `src/finding_extractor/batch_cli.py`: changed `print_once()` to return the state dict it loaded; watch loop uses that instead of re-reading.

## 2026-02-12 — Merge eval branch into dev + TTY-aware console colors

- Merged `feature/agent-iteration` into `dev` (fast-forward to `8ecabbc`), bringing eval harness updates plus logging integration follow-ups.
- Updated structured console logging to be TTY-aware:
  - `src/finding_extractor/logging_setup.py` now sets `ConsoleRenderer(colors=sys.stderr.isatty())` (with safe fallback to `False` on stream errors).
  - Keeps JSON mode behavior unchanged when `IPL_LOG_JSON=true`.
- Added test coverage for color behavior:
  - `tests/test_logging_setup.py`: verifies console renderer enables colors when stderr reports TTY.

## 2026-02-12 — Structured logging integration for eval harness

After rebasing onto the logging work from `dev`, wired the eval CLI and runner into the structured logging pipeline.

- `eval_cli.py`: added `configure_logfire(runtime="cli")` + `setup_logging()` at startup — same pattern as `cli.py` and `batch_cli.py`.
- `eval/runner.py`: replaced `logging.getLogger()` with `structlog.get_logger()`.
- `tests/test_eval_cli.py`: added autouse fixture mocking `configure_logfire` and `setup_logging`.
- Updated `docs/configuration.md` — added eval settings to env var table and config.toml example.
- Updated `config.toml.example` — added eval settings.
- Updated `docs/eval-internals.md` — noted logging/logfire wiring in CLI architecture section.
- Updated `docs/logging-plan.md` — listed eval CLI as a wired runtime.

## 2026-02-12 — Structured logging setup (Stages 1–2 of logging plan)

Implemented process-global structured logging via `structlog` across all runtimes.

### New files
- `src/finding_extractor/logging_setup.py` — idempotent `setup_logging(settings, *, include_logfire_processor)` with `ConsoleRenderer`/`JSONRenderer` switch and optional Logfire processor.
- `tests/test_logging_setup.py` — idempotency, renderer switch, Logfire processor integration.

### Key design decisions
- **structlog stdlib integration** (`ProcessorFormatter` + `wrap_for_formatter`) — existing stdlib loggers get structured formatting automatically.
- **Idempotent setup** via module lock + `_configured` flag — safe to call from multiple entry points.
- **Runtime wiring**: API (`create_app`), CLI (`run_command`), batch CLI (group callback), and worker (`WORKER_STARTUP` hook) all call `setup_logging()` once at startup.
- **Worker cleanup**: moved `configure_logfire()` from per-job `_run_extraction_impl()` to TaskIQ `WORKER_STARTUP` event.

### Config additions
- `IPL_LOG_LEVEL` / `log_level` (default: `INFO`)
- `IPL_LOG_JSON` / `log_json` (default: `false`)

### Modified files
- `pyproject.toml` — added `structlog` dependency
- `src/finding_extractor/config.py` — added `log_level`, `log_json` settings
- `src/finding_extractor/api.py`, `cli.py`, `batch_cli.py`, `broker.py`, `tasks.py` — wired `setup_logging()` calls
- `docs/logging-plan.md` — marked Stages 1–2 implemented
- `docs/configuration.md`, `docs/extraction-usage.md` — documented new settings

## 2026-02-11 — Stage 2 Phase 1: Evaluation Harness (Minimal Viable Eval)

Implemented the evaluation harness for measuring extraction quality across prompt, model, and configuration changes.

### New files
- `src/finding_extractor/eval/` subpackage: `__init__.py`, `models.py`, `matching.py`, `evaluators.py`, `task.py`, `datasets.py`, `runner.py`
- `src/finding_extractor/eval_cli.py` — Click CLI with `run` subcommand
- `evals/datasets/smoke.yaml` — 2-case dataset from few-shot examples (CT abdomen + XR chest)
- `tests/test_eval_matching.py`, `tests/test_eval_evaluators.py`, `tests/test_eval_cli.py`

### Key design decisions
- **pydantic-evals** for dataset management, evaluator orchestration, and reporting — uses built-in `max_concurrency` for parallel case execution.
- **Jaccard token similarity** matching algorithm (no external NLP deps) with presence bonus (+0.1) and greedy best-match. Threshold default: 0.3.
- **6 custom evaluators**: FindingDetection (precision/recall/F1), PresenceClassification, Location, Attribute, VerbatimQuote, NonFindingClassification.
- **VerbatimQuoteEvaluator** reuses `check_verbatim()` from `agent.py` for consistency.
- **asyncer.runnify()** bridges async runner to synchronous Click CLI (same pattern as batch_cli.py and cli.py).

### Modified files
- `pyproject.toml` — added `finding-extractor-eval` entry point
- `src/finding_extractor/config.py` — added eval settings (`eval_run_dir`, `eval_workers`, `eval_timeout_seconds`, `eval_dataset_dir`)
- `.gitignore` — added `evals/runs/` and `.eval_runs/`
- `Taskfile.yml` — added `eval:smoke` task, added eval test files to `test:unit`
- `docs/extractor-agent-plan.md` — updated Stage 2 with Phase 1 completed status and Phase 2/3 plans
- `README.md` — added eval CLI commands and doc links
- `docs/eval-usage.md` — new user guide
- `docs/eval-internals.md` — new developer guide

### Run output structure
```
.eval_runs/<run_id>/
  run_config.json    # Frozen configuration
  results.json       # Aggregate averages + per-case scores
  results.jsonl      # One JSON line per case
```

**Verification:** `task lint` clean, `task test` passed (no regressions).

## 2026-02-11 — Fix batch_cli integration gaps after Stages 0/1/1.5 rebase

After rebasing `feature/agent-iteration` (Stages 0/1/1.5) onto `dev`, a code review identified 4 integration gaps in `batch_cli.py`. The batch CLI was written on `dev` before the feature work landed, so it didn't account for new DB columns, usage data, reasoning validation, or changed `--validate` semantics.

### Fixes applied
- **Reasoning preflight** (`batch_cli.py`): Added `validate_reasoning_for_model()` call in `_resolve_run_options()` so invalid model/reasoning combos (e.g. `ollama:llama4 --reasoning high`) fail fast at batch start instead of per-file.
- **Usage in `_storage` output** (`batch_cli.py`): `_process_one_file()` now serializes `storage_metadata.usage` into the `_storage` dict, matching the single-file CLI's `format_json_output()` pattern.
- **Migration preflight** (`store.py`, `batch_cli.py`, `cli.py`): Added `ExtractionStore.check_migration_current()` which checks the `alembic_version` table against `EXPECTED_REVISION`. Both CLIs call this **before** `store.init()` and fail fast with an actionable error directing users to run `task db:migrate` if the DB is at the wrong revision. Batch CLI writes terminal `"failed"` state before raising so `status --watch` doesn't hang.
- **`--validate` help text** (`batch_cli.py`, `cli.py`, `docs/extraction-usage.md`): Clarified that `--validate` runs coverage analysis only — verbatim checking is handled by the agent's output validator with retries.

### Tests
- `tests/test_batch_cli.py`: reasoning preflight rejection, usage in output, migration preflight writes terminal failed state.
- `tests/test_cli.py`: migration preflight rejects outdated DB with actionable error.

**Verification:** `task lint` clean, `task test` passed.

## 2026-02-11 — Local batch extraction CLI (interactive + detached) + config integration

Implemented a first-class local batch runner without introducing new DB tables or direct TaskIQ wiring.

- Added `finding-extractor-batch` CLI (`src/finding_extractor/batch_cli.py`):
  - `run` command with `--mode interactive|detached`
  - bounded concurrency (`workers`), per-file timeout, retries, resume behavior
  - per-worker elapsed runtime in status output
  - `status` command with optional `--watch`
  - local run-state artifacts under `.batch_runs/<run_id>/`
- Added shared extraction pipeline module (`src/finding_extractor/extraction_pipeline.py`) used by both:
  - `finding-extractor` (single-file CLI)
  - `finding-extractor-batch`
  This removes duplicated extraction/validation/persistence pipeline logic.
- Added batch settings to centralized config (`src/finding_extractor/config.py`):
  - `batch_run_dir`, `batch_workers`, `batch_timeout_seconds`, `batch_retries`
  - `batch_status_interval_seconds`, `batch_output_suffix`, `batch_resume`
  with env aliases `IPL_BATCH_*` and `config.toml` support.
- Wired new CLI entrypoint in `pyproject.toml`.
- Added/updated tests:
  - `tests/test_batch_cli.py`
  - `tests/test_config.py`
  - `tests/test_cli.py` (patched to shared pipeline seam)
- Updated docs and workflows:
  - `README.md`
  - `docs/extraction-usage.md`
  - `docs/dev-ops.md`
  - `docs/configuration.md`
  - `docs/human-review-workflow.md`
  - `Taskfile.yml` (`task extract:example3`)

## 2026-02-11 — Rebase integration: Stages 0/1/1.5 onto extraction_pipeline refactor

Rebased the `feature/agent-iteration` branch (Stages 0, 1, 1.5) onto `dev`, which had gained a shared `extraction_pipeline.py` module and `batch_cli.py`. The original feature commits modified `cli.py` inline; dev moved that logic into `extraction_pipeline.py`. Squashed the 2 feature commits into 1 before rebasing to avoid resolving the same 3-file conflict set twice.

### Non-trivial integration decisions

- **`status_callback` threaded through `extraction_pipeline.py`**: Since `run_extraction_pipeline()` is where `extract_findings()` is called, the callback had to be added there (not in cli.py). Added `status_callback: Callable[[str], Awaitable[None]] | None = None` parameter and an `_emit()` helper for conditional emission. Pipeline-level status messages ("Validating model configuration...", "Saving to database...", "Done.") are emitted from here, while agent-level messages ("Calling model...", "Model call complete") come from `extract_findings()` via the same callback.
- **`ExtractionResult` unwrapping in `extraction_pipeline.py`**: The `extract_findings()` return type changed from `ReportExtraction` to `ExtractionResult`. The unwrapping (`extraction_result.extraction`, `extraction_result.usage`) now happens in `run_extraction_pipeline()`.
- **`usage` field on `StorageMetadata`**: Added `usage: ExtractionUsage | None = None` to the dataclass (now in `extraction_pipeline.py`, not `cli.py`). Passed through to `create_extraction()` and the `StorageMetadata` constructor.
- **Reasoning validation in `extraction_pipeline.py`**: `validate_reasoning_for_model()` call moved from the old `cli.py` inline code into `run_extraction_pipeline()`, benefiting both CLI and batch_cli.
- **`cli.py` stays thin**: `_run_pipeline()` creates a `_status_cb` closure that prints to stderr, passes it to `run_extraction_pipeline()`. Formatting functions (`format_json_output`, `format_table_output`) handle usage display.
- **Test pattern adapted**: All CLI tests mock `finding_extractor.cli.run_extraction_pipeline` (dev's pattern), not `extract_findings` (feature branch's old pattern). New tests (`usage`, `progress`, `reasoning rejection`) adapted accordingly.
- **`batch_cli.py` unchanged**: New `status_callback` param defaults to `None`, backward-compatible.
- **Click 8.3.x `mix_stderr` removal**: `CliRunner(mix_stderr=False)` removed — Click 8.3.x always separates stderr, so `result.stderr` works without it.

### Files resolved during rebase
| File | Resolution |
|------|------------|
| `docs/DEV_LOG.md` | Kept dev's batch CLI entry, added Stage 0/1/1.5 entries |
| `src/finding_extractor/cli.py` | Took dev's thin-wrapper structure, added usage formatting + status callback |
| `tests/test_cli.py` | Adapted all new tests to dev's `fake_run_extraction_pipeline` mock pattern |
| `src/finding_extractor/extraction_pipeline.py` | Edited (no conflict): added reasoning validation, ExtractionResult, usage, status_callback |

**Verification:** `task lint` clean, `task test` 152 passed.

## 2026-02-11 — Stage 1.5: Agent Status Callback

Added an optional async `status_callback` to `extract_findings()` so callers get progress messages from inside the extraction (model call, retries, completion) instead of silence during the LLM round-trip.

### Core changes
- Added `status_callback: Callable[[str], Awaitable[None]] | None` field to `ExtractorDeps` in `models.py`.
- Added `_emit_status()` async helper in `agent.py` that invokes the callback when present (no-op when `None`).
- `extract_findings()` accepts `status_callback`, passes it into deps, emits status before/after `agent.run()`.
- Made the output validator `async` to emit `"Retrying: verbatim validation failed (N error(s))"` on retry.
- Worker (`tasks.py`): closure writes status to DB via `store.update_job_status_message()`.
- CLI (`cli.py`): closure prints to stderr via `click.echo(..., err=True)`.

### Status messages emitted
| Point | Message |
|---|---|
| Before `agent.run()` | `"Calling model..."` |
| On verbatim validation retry | `"Retrying: verbatim validation failed (N error(s))"` |
| After `agent.run()` | `"Model call complete, processing results"` |

### Bug fixes (found during implementation)
- Fixed `ty` error in `cli.py:format_json_output`: narrowed `storage_dict.get("usage")` guard to `storage_metadata.usage is not None` so `ty` can prove `model_dump` is safe.
- Fixed `ty` error in `config.py:_find_forbidden_keys`: added explicit `dict[str, object]` local for the narrowed `isinstance(value, dict)` branch.

### Test and infrastructure updates
- `test_extraction.py`: 2 new `TestEmitStatus` tests (no-op and invocation).
- `test_tasks.py`: extended completed-job test to verify callback invocation and intermediate messages.
- `test_cli.py`: extended stderr test to verify agent-internal messages appear; updated all fake signatures.
- `test_api.py`: updated all fake `extract_findings` signatures to accept `status_callback`.
- `Taskfile.yml`: added `test_extraction.py`, `test_cli.py`, `test_models.py` to `test:unit` target.

### Docs updated
- `docs/extractor-agent-plan.md`: added Stage 1.5 section (completed), marked Stage 1 completed, added PydanticAI streaming to Later Improvements, updated Immediate Next Actions.
- `docs/extraction-internals.md`: added Status Callback section, updated test class list.
- `docs/extraction-usage.md`: updated Python API example with `status_callback` and `ExtractionResult` return type.

**Verification:** `task lint` clean, `task test` 152 passed, `task test:smoke` passed, `task test:integration` 11 passed / 2 skipped.

## 2026-02-11 — Stage 1: Status Messages for In-Flight Progress

Implemented `status_message` column on the `jobs` table and wired phase-boundary updates through the worker and CLI. (This work was done in the same session as Stage 0 but as a separate logical stage.)

- Added `status_message` nullable column to `jobs` table via Alembic migration `a3f1c8b2d4e6`.
- `mark_job_running/completed/failed` set bookend status messages automatically.
- Worker calls `store.update_job_status_message()` at each phase boundary (retrieving report, validating model, extracting, validating, saving).
- CLI emits equivalent progress to stderr via `click.echo(..., err=True)`.
- `status_message` exposed in `JobResponse` API model.

**Verification:** `task test` passed, `task test:smoke` passed.

## 2026-02-11 — Stage 0: Correctness and Contracts (extractor agent plan)

Implemented all Stage 0 deliverables from `docs/extractor-agent-plan.md`: reasoning validation, reasoning="none" consistency, and usage/token accounting.

### Reasoning validation
- Added `ReasoningLevel` Literal type in `models.py` as single source of truth.
- Added `VALID_REASONING_LEVELS` (derived via `get_args(ReasoningLevel)`), `validate_reasoning()`, and `validate_reasoning_for_model()` in `agent.py`.
- `PROVIDER_SUPPORTED_REASONING` matrix: Ollama accepts only `"none"`; OpenAI, Anthropic, Google accept all levels.
- Wired validation into API (`api_services.py` -> 422), CLI (`cli.py` -> fail-fast), and worker (`tasks.py` -> defense-in-depth).

### reasoning="none" fix
- OpenAI now sends explicit `reasoning_effort="none"` (was silently falling back to `None`/medium).
- Google now sends explicit `thinking_level="NONE"` (same issue).
- Anthropic already worked correctly (`{"type": "disabled"}`).

### Usage and token accounting
- Added `ExtractionUsage` Pydantic model (`requests`, `input_tokens`, `output_tokens`, `cache_read_tokens`, `cache_write_tokens`, `duration_ms`, `details`).
- Changed `extract_findings()` return type from `ReportExtraction` to `ExtractionResult` (frozen dataclass pairing extraction with usage).
- Usage captured from pydantic-ai `result.usage()` with `time.monotonic()` for duration; capture is best-effort with debug logging on failure.
- Added 7 nullable columns to `extractions` table via Alembic migration `7537480089ba`.
- Usage surfaced in API response models (`ExtractionSummaryResponse`, `ExtractionDetailResponse`) and CLI output (JSON `_storage.usage` and table token/duration lines).

### Tests
- `test_extraction.py`: `TestReasoningValidation` (8 tests), `TestOpenAINoneSettings`, `TestExtractionResult` (3 tests), updated existing provider settings tests.
- `test_api.py`: invalid reasoning 422, incompatible reasoning 422, extraction detail with usage round-trip.
- `test_cli.py`: incompatible reasoning rejection, JSON output with usage serialization.
- `test_migrations.py`: updated for new migration head.

### Code review fixes (same session)
- Fixed `format_json_output` serialization bug: `asdict()` on `StorageMetadata` couldn't serialize Pydantic `ExtractionUsage`; now calls `.model_dump(mode="json")`.
- Removed dead `ReasoningLevel` type alias that was defined but unused (now properly imported and used).
- Removed redundant `validate_reasoning()` calls in `api_services.py` and `tasks.py` (already called internally by `validate_reasoning_for_model()`).
- Replaced silent `except Exception: pass` in usage capture with `logger.debug(..., exc_info=True)`.
- Regenerated migration with proper Alembic-style revision ID (`7537480089ba`) and consistent `sqlmodel.sql.sqltypes.AutoString()` types.

**Verification:** 142+ tests pass across all unit test modules.

## 2026-02-10 — Extractor UI CDN alignment + skill documentation cleanup

Aligned `extractor-ui/index.html` and `extractor-ui/app.js` with the project's Flowbite/Tailwind/Alpine CDN stack, and comprehensively fixed all skill reference docs.

### Extractor UI changes (Phase 1–2 of refactoring plan)
- **CDN stack**: Replaced Tailwind v3 Play CDN (`cdn.tailwindcss.com`) with Flowbite CSS 4.0.1 + Tailwind v4 browser CDN (`@tailwindcss/browser@4`) + `@custom-variant dark` for class-based dark mode. Flowbite CSS loads first (includes a complete Tailwind v4 build), then the browser CDN adds dynamic utility generation and class-based dark mode.
- **Flowbite 4.0.0 → 4.0.1**: Updated both CSS and JS CDN references.
- **FOUC script**: Changed from system-preference-based to dark-by-default (`localStorage 'light'` opts out).
- **Dark mode toggle**: Renamed `isDark` → `darkMode`, added `$watch` reactive pattern, removed imperative `toggleDarkMode()` method, updated HTML to `@click="darkMode = !darkMode"` with `x-show` on SVG icons.
- **Semantic token migration rejected**: Flowbite v4 semantic tokens (`text-heading`, `bg-brand`, etc.) require a build step; they resolve to nothing in CDN-only setups. Sticking with classic `dark:` prefix approach.

### Skill documentation overhaul
- **`SKILL.md`**: Corrected version matrix, CDN stack (Tailwind v4, not v3), anti-patterns, and added explanatory note that Flowbite CSS includes a complete Tailwind v4 build.
- **`references/component-templates.md`**: Rewrote all 21 component template sections to use classic `dark:` prefix classes instead of semantic tokens. Every template is now copy-paste ready for CDN-only projects.
- **`references/alpine-patterns.md`**: Fixed ~20 code examples that used semantic tokens (forms, badges, cards, buttons, nested components, star ratings, modals).
- **`references/color-patterns.md`**: Corrected CDN setup section (Tailwind v4, not v3), removed stale "Why not Tailwind v4?" callout. Semantic token mapping table preserved as future reference.

### Planning docs
- **`docs/extractor-ui-refactoring.md`**: Rewritten to reflect completed state (phases 1–2 done, semantic tokens rejected with rationale).
- **`docs/viewer-refactoring.md`**: New detailed plan for aligning the IPL viewer with the same CDN stack (5 concrete items with before/after code, recommended order, verification steps).

### Cleanup
- Deleted 12 test-artifact screenshot PNGs from repo root.

**Verification:** All 48 Playwright tests pass (`uv run pytest tests/test_ui.py -v`).

## 2026-02-10 — Shared `validate_model_id` policy + runtime enforcement

Implemented a shared model-id validation module and wired it into all runtime entry points.

- Added `src/finding_extractor/model_policy.py`:
  - shared model-id parsing and policy helpers
  - `validate_model_id(...)` with explicit Google/Anthropic constraints
  - hard rejection of `google-vertex:*` (require `google-gla:*`)
- Enforced policy in:
  - `src/finding_extractor/config.py` (`default_model` validated at settings load)
  - `src/finding_extractor/api_services.py` (pre-enqueue API validation -> `422`)
  - `src/finding_extractor/tasks.py` (worker defense-in-depth validation)
  - `src/finding_extractor/cli.py` (fail-fast CLI validation)
  - `src/finding_extractor/model_catalog.py` (shared policy helpers now central source)
- Added regression coverage:
  - `tests/test_model_policy.py`
  - `tests/test_api.py` invalid-model `422` case
  - `tests/test_tasks.py` invalid-model `invalid_request` case
  - `tests/test_cli.py` invalid-model fail-fast case
  - `tests/test_config.py` invalid default-model settings validation case

## 2026-02-10 — `/api/models` implemented with Redis cache + SOTA filtering

Implemented provider-backed model discovery for the API and exposed a stable `GET /api/models`
contract for clients.

- Added `src/finding_extractor/model_catalog.py`:
  - provider discovery (OpenAI, Anthropic, Google Gemini)
  - latest-generation-per-tier filtering to suppress superseded model generations
  - Redis-backed catalog cache with refresh lock and on-demand refresh behavior
  - deterministic model tie-breaking for stable results across refreshes
  - canonical provider-prefix handling for default model matching
  - graceful Redis-degraded fallback (no endpoint 500 on cache outage)
  - explicit provider policy gates:
    - Anthropic restricted to `4.5` / `4.6`
    - Gemini restricted to `3.x` `pro`/`flash`
    - no permissive fallback for known providers when models fail policy parsing
- Added model catalog dependency + route wiring:
  - `src/finding_extractor/api_dependencies.py`
  - `src/finding_extractor/api_routes.py`
  - `src/finding_extractor/api.py` lifecycle initialization/shutdown
  - `src/finding_extractor/api_models.py` response contract + mapping
- Extended centralized settings in `src/finding_extractor/config.py`:
  - provider API key fields
  - `IPL_MODEL_LIST_UPDATE_INTERVAL` (default 48h)
- Added regression coverage:
  - `tests/test_api.py` endpoint contract test for `/api/models`
  - `tests/test_model_catalog.py` supersession filtering tests
  - `tests/test_config.py` settings coverage for new env vars
- Updated docs:
  - `docs/api-server.md`
  - `docs/api-usage.md`
  - `docs/api-internals.md`
  - `docs/dev-ops.md`

## 2026-02-10 — API module refactor (routers/services/contracts split)

Refactored the API layer into dedicated modules while preserving existing endpoint behavior and
contracts.

- Added:
  - `src/finding_extractor/api_routes.py` (`/api/*` route handlers)
  - `src/finding_extractor/api_services.py` (orchestration helpers for lookups/enqueue)
  - `src/finding_extractor/api_models.py` (request/response models + mapping helpers)
  - `src/finding_extractor/api_dependencies.py` (shared dependencies)
- Updated `src/finding_extractor/api.py` to focus on app composition, lifecycle wiring, and
  health/readiness endpoints.
- Kept `finding_extractor.api:app` entrypoint stable for runtime and worker DI integration.
- Updated tests for relocated enqueue-id monkeypatch target
  (`finding_extractor.api_services.uuid4`).
- Validation:
  - `task lint` passed
  - `task test:unit` passed

## 2026-02-10 — Data-model Track A started (strict model base + shared aliases)

Started data-model consolidation Track A with low-risk steps that do not change schema or API
contracts.

- Added `src/finding_extractor/base.py` with `StrictBaseModel` (`extra="forbid"`).
- Updated `src/finding_extractor/models.py` to inherit from `StrictBaseModel` and introduced
  shared aliases:
  - `CorrectionType`
  - `CorrectionStatus`
  - `JobStatus`
  - `Presence`
- Updated API request/response models in `src/finding_extractor/api.py` to inherit from
  `StrictBaseModel`.
- Updated `src/finding_extractor/store.py` to import shared aliases from `models.py` and build
  SQL `CHECK` constraints from those aliases to keep Python/DB status values aligned.
- Reduced API endpoint boilerplate in `src/finding_extractor/api.py` by centralizing repeated
  store->response mapping in helper functions (no response contract changes).
- Reduced store-layer boilerplate in `src/finding_extractor/store.py` by centralizing repeated
  row->stored-dataclass mapping in helper functions (no boundary/contract changes).
- Track A core cleanup slices are now complete; Track B remains deferred/optional.
- Validation:
  - `task lint` passed
  - `task test:unit` passed

## 2026-02-10 — Config plan doc cleanup + schema migration runbook

Cleaned up planning docs to match implemented config behavior and added an explicit
schema-migration runbook for future contributors/agents.

- `docs/config-plan.md` now reflects the actual flat `Settings` implementation and real
  changed files.
- Added `docs/schema-migrations.md` with first-time DB adoption, schema-change workflow,
  and required PR checklist commands.
- Added cross-links in:
  - `README.md`
  - `docs/dev-ops.md`
  - `docs/persistence-internals.md`
  - `docs/migration-architecture.md`

## 2026-02-10 — Env-first config centralization (Phase 1/2)

Implemented centralized runtime settings using `pydantic-settings` and removed ad-hoc env
resolution from backend runtime modules.

- Added `src/finding_extractor/config.py`:
  - `Settings` with env-first defaults and compatibility aliases for existing env names.
  - cached `get_settings()` and `clear_settings_cache()` helper.
- Wired settings usage in:
  - `src/finding_extractor/agent.py`
  - `src/finding_extractor/api.py`
  - `src/finding_extractor/cli.py`
  - `src/finding_extractor/tasks.py`
  - `src/finding_extractor/broker.py`
- Added config regression coverage:
  - `tests/test_config.py`
  - `tests/conftest.py` cache-clear fixture for deterministic env tests.
- Updated workflow/docs:
  - `Taskfile.yml` (`test:unit` now includes `tests/test_config.py`)
  - `README.md`
  - `docs/config-plan.md`
  - `docs/data-model-plan.md`
  - `docs/api-server.md`
## 2026-02-10 — Alembic migration foundation implemented

Implemented the migration foundation so schema evolution no longer depends on `create_all`.

- Added Alembic scaffolding:
  - `alembic.ini`
  - `alembic/env.py`
  - `alembic/script.py.mako`
  - `alembic/versions/17f8ebc6c608_baseline_schema.py`
- Wired Alembic metadata/autogenerate to SQLModel tables and SQLite-safe batch mode.
- Added migration task commands in `Taskfile.yml`:
  - `db:migrate`, `db:migrate:stack`, `db:stamp:baseline`, `db:stamp:baseline:stack`, `db:revision`, `db:current`, `db:heads`, `db:check`
- Updated container packaging for migration support:
  - `Dockerfile` now includes `alembic/` and `alembic.ini` in the image.
- Added migration regression tests:
  - `tests/test_migrations.py`
  - Includes pre-Alembic adoption coverage (`create_all` schema -> `stamp` baseline -> `upgrade head`)
- Updated docs to reflect current policy and commands:
  - `docs/migration-architecture.md`
  - `docs/persistence-internals.md`
  - `docs/api-server.md`
  - `docs/dev-ops.md`
  - `README.md`
## 2026-02-10 — Readiness contract tightened for queue-backed extraction

Updated API readiness behavior so `/api/readyz` now checks extraction dependencies, not just DB reachability.

- Added broker-backend readiness check in `src/finding_extractor/api.py`:
  - `assert_broker_ready(...)` pings Redis through TaskIQ broker connection pool when available.
  - non-Redis test brokers (e.g. `InMemoryBroker`) are treated as ready to keep deterministic unit tests.
- Updated `/api/readyz` to return `503 Not ready` if either:
  - database access check fails, or
  - broker backend connectivity check fails.
- Added regression test in `tests/test_api.py`:
  - `test_readyz_returns_503_when_broker_backend_is_unavailable`.
- Updated docs for readiness semantics:
  - `docs/api-server.md`
  - `docs/api-internals.md`
  - `docs/api-usage.md`
  - `docs/dev-ops.md`

## 2026-02-10 — Correction target validation hardening

Hardened correction persistence so `update_finding` corrections cannot be stored without a resolvable target finding path.

- `src/finding_extractor/store.py` now rejects out-of-range `target_finding_index` for `update_finding` with:
  - `ValueError("update_finding target_finding_index does not exist in extraction findings")`
- API behavior remains contract-stable:
  - `src/finding_extractor/api.py` maps store `ValueError` to `422`
- Added regression coverage:
  - `tests/test_store.py` verifies invalid index raises and no correction row is persisted.
  - `tests/test_api.py` verifies invalid index returns `422` and correction list remains empty.
- Updated validation docs:
  - `docs/persistence-internals.md`
  - `docs/api-internals.md`
  - `docs/api-usage.md`
- Frontend impact:
  - No immediate UI code change required because current MVP UI only creates `comment` corrections (no `update_finding` form yet).
## 2026-02-09 — Lean backend workflow + integration hardening

Aligned backend workflow to a lean strategy while merging in full-stack integration improvements.

- Added `Taskfile.yml` as the primary workflow surface:
  - `lint` (ruff + ty)
  - `test` / `test:unit`
  - `test:smoke`
  - `test:integration`
  - `stack:up` / `stack:up:full` / `stack:down`
- Moved smoke-test logic to Python module:
  - `src/finding_extractor/smoke.py`
- Removed shell smoke wrapper (`scripts/smoke_api.sh`) to keep deep logic out of shell.
- Added full-stack integration assets from `dev` branch:
  - `Caddyfile` reverse proxy and Compose `caddy` service
  - Docker healthchecks and `service_healthy` startup ordering
  - `tests/test_integration.py` for browser -> proxy -> API -> worker -> Redis coverage
- Added explicit API health endpoints for operational probes:
  - `GET /api/healthz` (liveness)
  - `GET /api/readyz` (readiness)
- Completed targeted typing cleanup to keep strict `ty` checks viable:
  - Typed Anthropic thinking settings in `src/finding_extractor/agent.py`.
  - Tightened validation-result typing in `src/finding_extractor/cli.py`.
  - Used SQLModel `col(...).desc()` expressions in `src/finding_extractor/store.py`.
  - Added targeted test typing adjustments in `tests/test_extraction.py`, `tests/test_models.py`, and `tests/test_store.py`.
  - Kept canonical FastAPI CORS middleware usage with a narrowly scoped `ty` suppression in `src/finding_extractor/api.py`.

Scope decision:
- Keep default focus on unit/component + smoke.
- Keep full-stack integration tests optional and out of the default fast path.

## 2026-02-08 — Extraction frontend MVP

Built a zero-build static frontend for the extraction API using Alpine.js 3.x, Tailwind CSS, and Flowbite 4.0 (all via CDN). The SPA (`extractor-ui/index.html` + `extractor-ui/app.js`) implements the full MVP workflow: submit report, trigger extraction with optional model/reasoning overrides, poll job progress, view structured extraction results (findings with presence/location/attribute badges, non-finding text, validation), and add comment corrections. Hash routing drives five views; a `?mock` URL parameter activates an in-memory mock API layer for offline development. The frontend was validated against the running backend's OpenAPI schema, including response flattening for the nested `ExtractionDetailResponse` shape. 48 Playwright E2E tests (`tests/test_ui.py`) cover all views, routing, dark mode, and end-to-end flows. Static files are served by Caddy reverse proxy in production (see 2026-02-09 entry).

**Docs:** [`docs/extractor-frontend.md`](extractor-frontend.md) (plan + implementation status), [`docs/frontend-usage.md`](frontend-usage.md) (user guide with screenshots), [`docs/frontend-internals.md`](frontend-internals.md) (developer/agent reference).

## 2026-02-08 — FastAPI + TaskIQ API server MVP stabilization

Implemented and stabilized the API-server plan with a FastAPI HTTP surface, TaskIQ worker pipeline, and Dockerized local runtime:

- Added API layer and routes in `src/finding_extractor/api.py` (reports, extraction dispatch/status, extraction detail/list, corrections).
- Added broker/task modules in `src/finding_extractor/broker.py` and `src/finding_extractor/tasks.py`.
- Extended persistence in `src/finding_extractor/store.py` with:
  - SQLite WAL pragmas on connect
  - read APIs for reports/extractions
  - async `jobs` table lifecycle methods for polling semantics
- Added tests for API/store behavior and task error handling:
  - `tests/test_api.py`
  - `tests/test_store.py` updates
  - `tests/test_tasks.py`
- Added container/runtime artifacts:
  - `Dockerfile`
  - `docker-compose.yml`
  - `.dockerignore`
  - `scripts/smoke_api.sh`

Security hardening in this pass:

- Job failure payloads were sanitized to stable public error codes.
- Enqueue failures now persist as `enqueue_failed:queue_unavailable`.
- Worker failures now persist as `extraction_failed:*` without leaking raw exception text.
- Internal exception details remain in server logs.

Docs updated/added in this pass:

- Updated in-place plan/status doc: `docs/api-server.md`
- Updated persistence docs: `docs/persistence-usage.md`, `docs/persistence-internals.md`
- New docs:
  - `docs/api-usage.md`
  - `docs/api-internals.md`
  - `docs/dev-ops.md`
## 2026-02-08 — CLI persistence integration

Reintroduced optional persistence wiring in `finding-extractor` CLI using the existing async store API (`ExtractionStore`) instead of custom storage code. CLI now supports `--store/--no-store` and `--db-path`, writes `reports` + `extractions` when enabled, and includes run metadata in output (`_storage` for JSON and `PERSISTENCE` block for table format). The implementation uses a single async orchestration function bridged once with `asyncer.runnify(...)` at the CLI boundary.

Added CLI coverage for persistence behavior in `tests/test_cli.py`, including row creation and `_storage` metadata assertions.

## 2026-02-08 — Multi-provider model support (`957274e`)

The extraction agent was hardcoded to OpenAI. We refactored `agent.py` to detect the provider from the pydantic-ai model string prefix and dispatch to per-provider settings builders, so the same `--reasoning` flag now maps to OpenAI reasoning effort, Anthropic extended thinking, and Google thinking levels. Ollama is supported but has no thinking mechanism. This required no new dependencies — pydantic-ai already bundles all provider settings types. We also added `"none"` as a valid reasoning level in the CLI. Known issue: `--reasoning none` doesn't actually override agent-level defaults for OpenAI/Google due to a `None`-overloading problem in `extract_findings()`; tracked in `docs/extraction-internals.md` along with other follow-up items.

**Docs:** [`docs/extraction-usage.md`](extraction-usage.md) (user guide), [`docs/extraction-internals.md`](extraction-internals.md) (contributor guide with known issues and future work).

## 2026-02-08 — Async persistence layer + CLI deferral plan

Added a dedicated async persistence layer in `src/finding_extractor/store.py` using SQLModel + SQLAlchemy async (`sqlite+aiosqlite`). The schema now centers on three entities: `reports` (dedup by `text_hash`), `extractions` (run-level metadata + full JSON payload), and `corrections` (human feedback records with type/status and optional finding targeting). Persistence tests were added in `tests/test_store.py` using native `pytest-asyncio` async fixtures/tests.

We intentionally did **not** wire persistence into `finding-extractor` CLI in this change to keep scope clean and avoid mixing concerns with the already-committed agent/provider work. Instead, we documented a concrete integration plan in `docs/archive/persistence-cli-plan.md` (flags, output shape, async boundary pattern, test plan, rollout order).

Dependencies added in `pyproject.toml` / `uv.lock`:
- `sqlmodel`
- `sqlalchemy[asyncio]`
- `aiosqlite`

**Docs:** [`docs/persistence-usage.md`](persistence-usage.md), [`docs/persistence-internals.md`](persistence-internals.md), [`docs/archive/persistence-cli-plan.md`](archive/persistence-cli-plan.md), [`docs/database-layer.md`](database-layer.md).
