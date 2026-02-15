# Dev Log

## 2026-02-15 — Stream 1 Slice 2: modular reliability reconciliation + stage/unit diagnostics

Implemented Stream 1 modular runtime slice 2 in `src/finding_extractor/extraction_orchestrator.py` and `src/finding_extractor/tasks.py`.

- Added `PipelineDiagnostics` to orchestrator results and emitted parseable summary statuses for:
  - section extraction totals/success/failure/attempts
  - per-repair-attempt start + summary
  - repair exhaustion with remaining unit labels/error types
- Reconciled reliability modes with modular section failures:
  - `lenient`: unrecovered failed units now produce `completed_with_warnings` and `warning_payload.reason_categories=["coverage_gap"]`
  - `strict`: unrecovered failed units now terminate as failed with deterministic warning payload
- Added focused tests:
  - `tests/test_extraction_orchestrator.py` for diagnostics/status emission on repair exhaustion
  - `tests/test_tasks.py` for strict/lenient modular remaining-failure outcomes

Validation:

- `uv run pytest tests/test_tasks.py tests/test_extraction_orchestrator.py -q` -> 21 passed
- `task lint` -> clean
- `task test` -> 440 passed

Tradeoffs/risks:

- Strict-mode modular incomplete runs currently reuse `extraction_failed:validation_failed` to preserve existing public error contract; clients should use `warning_payload.reason_categories` to distinguish coverage-driven failures.
- Warning payload v1 does not yet expose a dedicated `section_failure_count`; modular failures are represented via `coverage_gap` and `coverage_warning_count`.

## 2026-02-15 — Dev Integration: reliability UI merged on top of backend/modular/eval closure

Integrated the ready workstreams into local `dev`:

1. `feature/reliability-contract-backend`
2. `feature/modular-pipeline-rollout-slice1`
3. `feature/eval-closure-stage3-evidence`
4. `feature/reliability-contract-ui`

Integration notes:

- Resolved merge conflicts in:
  - `src/finding_extractor/api_models.py`
  - `src/finding_extractor/store.py`
  - `docs/DEV_LOG.md`
  - `docs/extractor-agent-plans/stream-reliability-contract.md`
- Kept the canonical warning contract as `warning_payload` (removed obsolete `warnings` field conflict path).
- Preserved UI support for `completed_with_warnings` and validation-warning banner behavior.

Validation on integrated `dev`:

- `task lint` -> clean
- `task test` -> 437 passed
- `task test:ui` -> 58 passed (9 deselected)

## 2026-02-15 — Reliability contract backend/API (strict vs lenient + deterministic warnings)

Implemented Stage 3 reliability contract in backend/API with warning-capable terminal semantics.

- Added `reliability_mode` (`strict` default, `lenient`) to extraction trigger requests.
- Added terminal status `completed_with_warnings` and threaded it through models/store/API mappings.
- Added deterministic `warning_payload` schema on jobs:
  - `schema_version`, `reliability_mode`, ordered `reason_categories`
  - dropped finding/non-finding counts
  - validation/coverage warning counts
- Implemented strict/lenient worker behavior:
  - `strict`: validation errors fail with `extraction_failed:validation_failed` and warning payload
  - `lenient`: invalid spans are dropped before persistence; terminal status is `completed_with_warnings`
- Added migration `e8f4a1b2c3d4`:
  - adds `jobs.warning_payload_json`
  - expands job status check constraint to include `completed_with_warnings`
- Added/updated tests across `tests/test_store.py`, `tests/test_tasks.py`, and `tests/test_api.py`.

## 2026-02-15 — Core Modular Pipeline Slice 1 (Section Parallel + Targeted Repair)

Implemented the first behavioral modular-pipeline slice in orchestrator/task runtime, behind explicit rollout guards.

- `src/finding_extractor/extraction_orchestrator.py`
  - Added section-unit execution path in `run_orchestrated_extraction(...)` when modular mode is enabled.
  - Section units are derived from detected report sections (`findings`/`impression` prioritized), executed with bounded concurrency, and retried per failed unit only.
  - Added merge/dedupe for successful unit outputs, including `source_section` reconciliation to `"both"` when duplicate finding content appears in both sections.
  - Post-review fix: successful outcomes are sorted by `unit.index` before merge so repaired-unit success timing cannot reorder findings or alter `exam_info` selection.
  - Preserved legacy single-pass behavior when modular mode is disabled.
- `src/finding_extractor/config.py`
  - Added rollout controls: `IPL_MODULAR_PIPELINE_ENABLED` (default `false`), `IPL_MODULAR_PIPELINE_MAX_CONCURRENCY` (default `2`), `IPL_MODULAR_PIPELINE_REPAIR_ATTEMPTS` (default `1`).
- `src/finding_extractor/tasks.py`
  - Passed modular rollout settings into orchestrator without changing API contracts.

Tests added/updated:

1. `tests/test_extraction_orchestrator.py`
   - bounded parallelism limit
   - failed-unit-only retry flow
   - cross-section dedupe with `source_section="both"`
2. `tests/test_tasks.py`
   - worker-level modular mode wiring + targeted retry coverage
3. `tests/test_config.py`
   - defaults/env coverage for new modular settings

Validation:

- `uv run pytest tests/test_tasks.py -q` -> 12 passed
- `uv run pytest tests/test_extraction_orchestrator.py -q` -> 4 passed
- `task lint` -> clean
- `task test` -> 432 passed

Tradeoffs/risks:

1. Modular mode currently proceeds with successful units when some repaired units still fail; this improves availability but can reduce completeness for that run.
2. Rollout is intentionally default-off to avoid unmeasured extraction-behavior drift until integration/runtime evidence is collected.

## 2026-02-15 — Stage 3 Eval Closure: Prompt Refactor + Section Detection Evidence

Ran before/after `eval:comprehensive` comparing Stage 3 prompt/parser changes against pre-Stage-3 baseline.

- **Baseline**: `baseline-pre-stage3` @ commit `815fdb1` (5/9 cases, 4 timeouts)
- **Candidate**: `eval-20260215-103012-ad5468da` @ commit `03ea0e2` (7/9 cases, 2 timeouts)
- **Model**: `openai:gpt-5-mini`, reasoning `medium`

Key metric deltas (4 common cases):

| Metric | Candidate | Baseline | Delta |
|--------|-----------|----------|-------|
| `finding_f1` | 0.950 | 0.946 | +0.004 |
| `presence_accuracy` | 0.983 | 0.950 | +0.033 |
| `verbatim_pass` | 100% | 100% | 0 |

**Decision: ACCEPTED.** No material regression on 4 common cases. Single-run comparison; baseline used `retries=1` vs candidate `retries=0` (see limitations in full evidence). Stage 3 closed. See `docs/extractor-agent-plans/stream-eval-closure.md`.

## 2026-02-15 — Stage 3: Reliability Contract UI — Warning Lifecycle

Implemented the UI surface for the `completed_with_warnings` job status from the Stage 3 reliability contract.

### UI changes (`extractor-ui/`)

1. **Polling**: `pollJob()` treats `completed_with_warnings` as terminal success (navigates to extraction detail).
2. **Extracting view**: Spinner hidden for warning status; heading shows "Extraction Completed with Warnings"; amber status badge added.
3. **Warning banner**: Amber alert banner on extraction detail view when `validation_result` has any warnings/errors, with issue count.
4. **Mock mode support**: `?warnings` query flag returns a warning-status job and warning-bearing extraction payload.

### Playwright tests

Added `TestWarningDisplay` (6 tests): banner visibility/count, hidden state without warnings, warning text rendering, and end-to-end submit-with-warnings flow.

## 2026-02-14 — Stage 3.5: Deterministic OIFM + Anatomic Location Coding Bridge

Implemented the baseline coding bridge — a deterministic, non-blocking, additive post-extraction step that maps free-text finding names to standardized OIFM codes and anatomic location references using the `findingmodel` and `anatomic-locations` packages.

### Coding pipeline (`coding_bridge.py`)

3-tier finding mapping strategy:

1. **Exact match** — `index.get(finding_name)` resolves by OIFM ID, name, or slug.
2. **Synonym match** — same `get()` call matches against synonym lists.
3. **Search** — `index.search(finding_name, limit=3)` uses hybrid BM25 + optional semantic search.
4. **Unresolved** — no match; finding lands in the unresolved list for future agent handoff.

Anatomic location mapping uses `anatomic-locations` package to map `FindingLocation` fields (specific_anatomy or body_region + laterality) to RadLex RID references.

### Data model additions (`models.py`)

- `CodingMethod` literal: `"exact"`, `"synonym"`, `"search"`, `"agent"`, `"unresolved"` — `"agent"` reserved for future Stage 7 LLM-based coding.
- `FindingCoding` — per-finding OIFM code result with method and alternates (no fake confidence scores).
- `LocationCoding` — per-finding anatomic RID result.
- `UnresolvedFinding` — minimal: just `finding_name` and `finding_index`.
- `AlternateCode` — candidate code with OIFM ID and name.
- `CodingBridgeResult` — run-level container with parallel arrays and summary counts.

### Error handling design

- **Infrastructure failures propagate** to the caller. `apply_coding()` does NOT swallow index-unavailable or DB download errors.
- **Per-finding failures are isolated** — one bad finding doesn't block the rest. Each finding gets its own try/except producing an empty `FindingCoding()`.
- **tasks.py is the single defense point** — catches any coding exception and sets `coding_result=None`, so extraction is never blocked.

### Integration

- **Feature flag**: `IPL_CODING_ENABLED` (default `false`) in `config.py`.
- **Task pipeline**: wired into `_run_extraction_impl()` after validation, before persistence. Lazy import of `coding_bridge` to avoid loading DuckDB indices when coding is disabled.
- **Persistence**: `coding_json` nullable TEXT column on `extractions` table (Alembic migration `c7a3d2e4f5b8`).
- **Dependencies**: `findingmodel>=1.0.0`, `anatomic-locations>=0.2.0` added to `pyproject.toml`.

### Code review fixes (same session)

Self-review identified and fixed 4 issues before commit:

1. **Removed `_empty_result()` data integrity bug** — helper set `unresolved_count=N` but `unresolved=[]`, producing inconsistent state. Removed the helper and the outer try/except from `apply_coding()` entirely.
2. **Removed fake confidence scores** — `confidence: float` on `FindingCoding`/`LocationCoding` and `score: float` on `AlternateCode` were hardcoded constants pretending to be real scores. Removed all three. The `method` field already conveys the resolution tier.
3. **Eliminated double defense** — follows from fix 1. `apply_coding()` no longer has "never raises" semantics; infrastructure failures propagate. `tasks.py` is the single catch point.
4. **Simplified `UnresolvedFinding`** — removed `reason: Literal[...]` and `candidates: list[AlternateCode]` fields that were never populated. Only `finding_name` and `finding_index` remain.

### Files created

| File | Description |
|------|-------------|
| `src/finding_extractor/coding_bridge.py` | Deterministic mapping pipeline |
| `alembic/versions/c7a3d2e4f5b8_add_coding_json.py` | Migration for coding_json column |
| `tests/test_coding_bridge.py` | 12 unit tests |

### Files modified

| File | Changes |
|------|---------|
| `pyproject.toml` | Added `findingmodel>=1.0.0`, `anatomic-locations>=0.2.0` |
| `src/finding_extractor/models.py` | Added `CodingMethod`, `AlternateCode`, `FindingCoding`, `LocationCoding`, `UnresolvedFinding`, `CodingBridgeResult` |
| `src/finding_extractor/config.py` | Added `coding_enabled` feature flag |
| `src/finding_extractor/store.py` | Added `coding_json` column, updated `create_extraction()` to accept `CodingBridgeResult` |
| `src/finding_extractor/tasks.py` | Wired coding bridge call after validation |
| `tests/test_tasks.py` | Added 3 integration tests (coding enabled/disabled/failure) |
| `tests/test_migrations.py` | Updated expected head revision to `c7a3d2e4f5b8` |
| `docs/extractor-agent-plans/stream-coding-bridge.md` | Full rewrite with what shipped, immediate next steps, agent transition design |

### Immediate next steps (documented in plan doc)

1. **Index lifecycle management** — `apply_coding()` opens fresh indices per call. Should open once at worker startup and reuse.
2. **Use `region` parameter on `AnatomicLocationIndex.search()`** — pass `body_region` as a filter to improve location match quality.

### Agent transition architecture

The deterministic layer is explicitly a minimal first pass. Key design decisions for future Stage 7 agent-based coding:
- `CodingMethod` includes `"agent"` — reserved now so schema doesn't change when the agent arrives.
- The unresolved list is the natural agent handoff — captures exactly the findings the deterministic layer couldn't resolve.
- `apply_coding()` is the stable interface — callers don't know if coding came from lookup or an agent.
- A single `CodingBridgeResult` can mix deterministic and agent-coded findings.

**Verification:** `task lint` clean, 48 targeted tests passing (12 in `test_coding_bridge.py`, 12 in `test_tasks.py`, plus store/migration tests).

## 2026-02-14 — Runtime Guard + Progress DX Hardening (Eval + Batch)

Added shared runtime preflight guard for both eval and batch CLIs via `src/finding_extractor/runtime_budget.py`.

- `finding-extractor-eval run` and `finding-extractor-batch run` now fail fast on high predicted runtime unless `--allow-slow` is passed.
- New flags on both CLIs: `--max-predicted-runtime-seconds` (default `900`) and `--allow-slow`.
- Eval runner now emits non-TTY heartbeat progress messages in addition to native TTY progress.
- Eval default retries changed from `1` to `0` (`src/finding_extractor/config.py`, `config.toml.example`, docs).
- Updated batch examples/docs/tasks to include explicit long-run override where appropriate.

## 2026-02-14 — Stage 5 Slice 1: Provider Module Refactoring + OpenRouter Support

Extracted provider-specific settings logic into dedicated module and added OpenRouter as 5th provider.

**Provider module creation**: New `src/finding_extractor/providers.py` with 215 lines extracted from `agent.py`. Contains provider detection, reasoning validation, and settings builders for all 5 providers (OpenAI, Anthropic, Google, OpenRouter, Ollama). Public API: `detect_provider()`, `get_model_settings()`, `validate_reasoning_for_model()`. Agent module reduced by ~170 lines.

**OpenRouter integration**: Added as first-class provider with `openrouter:` prefix (e.g., `openrouter:meta-llama/llama-3.1-70b`). Uses PydanticAI's native `OpenRouterModelSettings` with effort-based reasoning (low/medium/high, maps `minimal` → `low`). Config via `OPENROUTER_API_KEY` environment variable. Catalog discovery deferred (model space too large/diverse for SOTA filtering).

**Architecture refinement**: Consolidated duplicate provider detection logic by creating canonical `PROVIDER_PREFIX_MAP` in `model_policy.py`. `providers.py` now imports instead of maintaining duplicate dictionary. Added module docstrings clarifying boundaries: `model_policy.py` (validation, detection, SOTA) vs `providers.py` (runtime settings).

**User documentation**: Added OpenRouter to provider table in `docs/extraction-usage.md`. Added Ollama setup section with `OLLAMA_BASE_URL` requirement explanation. Updated `docs/configuration.md` with `OPENROUTER_API_KEY` and Ollama config. Added provider overview to `README.md` (5 providers with quick start).

**Tests**: 20 new tests (OpenRouter settings/validation, Anthropic budget verification, Google thinking completeness). All 385 tests passing, lint clean.

**Commits**: `07ebdd7`, `47e1383`, `ce4124a` on `feature/provider-expansion` branch.
## 2026-02-13 — Stage 3 Stabilization: Parser Bug Fix + Workflow Improvements

Fixed critical section parsing bug and improved development workflow.

**Section parser correctness fix**: The title-case header regex `_RE_TITLE` was using `\s` in the header name pattern, which includes newlines. This caused the pattern to match across line boundaries and prevent later headers (like `Impression:`) from being detected. Fixed by changing `[A-Za-z\s]+` to `[A-Za-z \t]+` (allows spaces/tabs but not newlines) and updating colon suffix from `:\s` to `:(?:[ \t]|$)` (allows space/tab or end-of-line). Added 3 regression tests.

**UI test workflow**: Added `test:ui` task to Taskfile.yml for running Playwright UI tests explicitly. Updated README.md, CLAUDE.md, and testing-practices.md with command documentation. Preserves default behavior (UI tests excluded from `task test`).

**Plan documentation alignment**: Marked Phase 3 as "IN PROGRESS - awaiting eval evidence" and added note requiring before/after `eval:comprehensive` runs. Tagged Stage 2 exit criteria with [IN PROGRESS] and [DEFERRED] status for transparency.

**Validation**: 151 targeted tests + 48 UI tests passing, ruff clean.

## 2026-02-13 — Stage 3 Phase 3: Report Preprocessing + Source Section Tracking

Three problems addressed: no structural hints for the model, overly restrictive impression handling, and no way to track where findings came from.

**New module `preprocess.py`**: Regex-based section detection with whitelist-only header matching (13 aliases → 7 canonical names, 4 priority patterns). Auto-generates section hints for the LLM prompt when sections are detected. Serialization via Pydantic `TypeAdapter` for DB persistence.

**`source_section` on `ExtractedFinding`**: Optional `Literal["findings", "impression", "both"] | None`. Stored in JSON blob — no migration needed, backward compatible.

**DB migration `b5e2a9f1c3d7`**: Nullable `section_structure_json` TEXT column on `reports` table. `upsert_report()` computes sections at ingestion and lazy-backfills pre-existing reports.

**Prompt changes**: Rewrote `DEDUPLICATION_BLOCK` (6 rules with source tracking; impression now allows unique item extraction). Updated `NON_FINDING_BLOCK` impression entry to cross-reference `SECTION PRIORITY`. Added `source_section` to `OUTPUT_FORMAT_BLOCK` and both example YAML files.

**Agent integration**: `build_prompt()` calls `preprocess_report()` transiently (no DB dependency). `upsert_report()` persists sections for future use.

**Tests**: 30 new in `test_preprocess.py`, plus updates to `test_prompt.py`, `test_models.py`, `test_extraction.py`, `test_store.py`, and `test_migrations.py`.

## 2026-02-12 — Stage 3 Phase 2: Schema-Driven Output Guidance

Tightened the extraction prompt with 5 targeted changes addressing impression handling, deduplication, presence disambiguation, attribute key expansion, and example cleanup.

### Prompt changes

1. **New `DEDUPLICATION_BLOCK`** — 5 rules covering section priority (body text > impression), impression routing to `non_finding_text`, one-entry-per-finding dedup, impression-only exception, and body-text authority for details. Inserted between `CORE_INSTRUCTIONS_BLOCK` and `PRESENCE_BLOCK`.
2. **Fixed "suggestive of" contradiction** — Rule 10 in `CORE_INSTRUCTIONS_BLOCK` listed "suggestive of" as a trigger for `possible`, but the CT abdomen example marks "suggestive of fatty infiltration" as `present`. Removed inline examples from rule 10; it now defers to `PRESENCE_BLOCK`.
3. **Presence disambiguation** — Added subsection to `PRESENCE_BLOCK` with explicit guidance: observation definitively seen + hedging label = `present`; diagnosis itself uncertain = `possible`. Includes concrete examples and a key test question.
4. **Expanded `ATTRIBUTES_BLOCK`** — Split into primary (6 keys) and additional (4 keys: `obstruction`, `characterization`, `caliber`, `patency`) hierarchy. Added guidelines: prefer primary keys, do NOT use "location" as attribute key, keep values concise.
5. **Strengthened `NON_FINDING_BLOCK`** — Impression entry changed from passive "findings here are typically restated" to directive "DO NOT extract findings from here."

### Example cleanup

- Changed `key: location` → `key: fracture_position` in `xr_chest.yaml` (2 occurrences) to align with new "Do NOT use location as attribute key" guideline.

### Tests

- 4 new tests: `test_deduplication_block`, `test_attributes_block_additional_keys`, `test_presence_block_disambiguation`, `test_non_finding_block_impression_instruction`.
- Updated `test_contains_all_blocks` (added `SECTION PRIORITY` assertion) and `test_blocks_in_order` (added `SECTION PRIORITY`, switched to `##`-prefixed section markers for uniqueness since rule 10 now references `PRESENCE VALUES`).

### Files modified

| File | Changes |
|------|---------|
| `src/finding_extractor/prompt.py` | Add `DEDUPLICATION_BLOCK`, fix rule 10, expand `PRESENCE_BLOCK`, expand `ATTRIBUTES_BLOCK`, strengthen `NON_FINDING_BLOCK`, update `_PROMPT_BLOCKS` list |
| `src/finding_extractor/examples/xr_chest.yaml` | Change `key: location` → `key: fracture_position` (2 places) |
| `tests/test_prompt.py` | Add 4 new tests, update 2 existing ordering/completeness tests |
| `docs/extractor-agent-plan.md` | Add Phase 2 deliverables section |
| `docs/DEV_LOG.md` | This entry |

**Verification:** `task lint` clean, `task test` 322 passed, prompt size increased ~200 tokens (19,764 → 22,120 chars).

## 2026-02-12 — Stage 3 Phase 0 + Phase 1: Test Fixes + Prompt Structure Split

### Phase 0: Green Baseline

Fixed pre-existing test failures to establish a truly green baseline before prompt refactoring.

- **UI test fix**: Added `aria-label="Your name"` to correction form input in `extractor-ui/index.html` — Playwright's `get_by_role("textbox", name="Your name")` now matches (previously matched against placeholder text "Your name (optional)").
- **Event loop isolation**: Added `@pytest.mark.ui` marker to all `test_ui.py` test classes and registered it in `pyproject.toml`. Added `addopts = "-m 'not ui and not integration'"` so bare `pytest tests/` no longer causes Playwright sync API + pytest-asyncio event loop conflicts (19 cascade errors eliminated).

### Phase 1: Prompt Structure Split + Example Externalization

Split the monolithic `INSTRUCTIONS` f-string (~92 lines) and hardcoded examples (~513 lines) into composable, testable modules.

**Architecture:**
- `examples/__init__.py` owns YAML data loading (`load_example`, `load_examples`) and backward-compatible accessors
- `prompt.py` owns prompt block constants, example formatting, and `build_system_prompt()` assembly
- Dependency flow is one-directional: `agent.py → prompt.py → examples/`

**New files:**
- `src/finding_extractor/prompt.py` — 7 prompt block constants + `build_system_prompt()` assembly
- `src/finding_extractor/examples/ct_abdomen.yaml` — CT abdomen few-shot example (was Python object construction)
- `src/finding_extractor/examples/xr_chest.yaml` — Chest XR few-shot example (was Python object construction)
- `tests/test_prompt.py` — 17 tests covering blocks, YAML loading, formatting, and assembly

**Modified files:**
- `src/finding_extractor/examples.py` → `src/finding_extractor/examples/__init__.py` — owns YAML loading via `importlib.resources` + backward-compatible accessors (~48 lines, down from 513 of hardcoded Pydantic objects)
- `src/finding_extractor/agent.py` — removed `INSTRUCTIONS` constant and `_build_instructions()`; now imports `build_system_prompt` from `prompt.py`; updated module docstring
- `tests/test_extraction.py` — removed redundant `TestInstructions` (covered by `test_prompt.py`)
- `Taskfile.yml` — added `test_prompt.py` to `test:unit` file list

**Verification:**
- Character-for-character equivalence: `build_system_prompt()` output is identical to old `_build_instructions()` (19,764 chars)
- YAML round-trip: both examples validate cleanly as `ReportExtraction` and produce identical `model_dump()` output
- YAML files cleaned: optional null fields (e.g. `laterality: null`) removed for readability without affecting prompt output
- All 318 unit tests pass + all 48 UI tests pass, lint clean
- Added `pyyaml>=6.0` as explicit dependency (was transitive)

## 2026-02-12 — Stage 2 Phase 3.5: Replace Bespoke Reporting with pydantic-evals Native Reporting

Replaced ~300 lines of hand-rolled text formatting in `reporting.py` with pydantic-evals native `EvaluationReport.print()` Rich output.

### report.json persistence

- `_save_report()` in `runner.py` serializes `EvaluationReport` via `EvaluationReportAdapter.dump_python(mode="json")` after each eval run.
- Large fields (inputs, output, expected_output) nulled out for storage efficiency.
- `experiment_metadata` stores model, dataset, reasoning, duration, and thresholds — rendered as a Rich panel header by pydantic-evals.

### Native display

- `display_report()` — single-run view via `report.print(include_reasons=True)`.
- `display_comparison(primary, compare)` — diff view showing change from primary to compare.
- `display_case_detail()` — filters report to single case, prints with optional comparison.

### Legacy fallback

- Runs without `report.json` get `print_legacy_summary()` — minimal averages table with note to re-run.
- `--compare` and `--case` options require `report.json`; legacy runs get a helpful error message.

### Deleted bespoke code (~300 lines)

- `print_run_summary()`, `print_comparison()`, `print_case_detail()`
- `_print_case_detail_single()`, `_print_case_detail_comparison()`
- `_direction_arrow()`, `_format_metric_value()`, `_get_all_case_metrics()`, `_get_all_case_reasons()`
- `_KEY_METRICS`
- `METRIC_DISPLAY_ORDER`, `_ordered_metrics()` (dead code after native reporting replaced bespoke formatting)

### Code review fixes

- **Comparison direction**: `display_comparison()` and `display_case_detail()` now correctly show "primary → compare" with positive deltas when compare improves.
- **No input mutation**: `_save_report()` sets `experiment_metadata` on the serialized dict, not the live `EvaluationReport` object.
- **Doc cleanup**: Removed implementation details (library names, rendering technology) from user-facing `eval-usage.md`.

### Files modified

| File | Changes |
|------|---------|
| `src/finding_extractor/eval/runner.py` | Add `_save_report()`, import `EvaluationReportAdapter`, call after eval |
| `src/finding_extractor/eval/reporting.py` | Delete ~300 lines bespoke formatting; add `load_report()`, `display_*()`, `print_legacy_summary()`; update `find_latest_run()` |
| `src/finding_extractor/eval_cli.py` | Rewire `report_command()` imports and routing |
| `src/finding_extractor/eval/__init__.py` | Update exports |
| `tests/test_eval_cli.py` | Rewrite `TestReportCli` fixtures and assertions; add 3 legacy fallback tests + direction test |
| `docs/eval-usage.md` | report.json in output, Rich format notes, legacy fallback |
| `docs/eval-internals.md` | New reporting module description, remove tech debt note, update runner/CLI sections |
| `docs/extractor-agent-plan.md` | Mark Phase 3.5 completed |
| `docs/DEV_LOG.md` | This entry |

**Verification:** `task lint` clean, all eval CLI tests pass (40 total including 4 new: 3 legacy fallback + direction), backward compatible with old results.json-only run directories.

## 2026-02-12 — Stage 2 Phase 3: Enhanced Eval Reporting

Added reason persistence, enhanced comparison output, and per-case detail view to the eval harness.

### Reason persistence

- `_extract_per_case_results()` in `runner.py` now captures `EvaluationResult.reason` into `score_reasons` and `assertion_reasons` dicts. Only included when non-empty (additive, backward-compatible schema change).
- `report.print(include_reasons=True)` enables richer live console output during eval runs.

### Enhanced comparison

- `print_comparison()` per-case section now shows all metrics (not just F1) using `METRIC_DISPLAY_ORDER`. Key metrics (finding_f1, presence_accuracy, verbatim_pass) always shown; others shown only when they differ between runs.
- New helpers: `_get_all_case_metrics()`, `_get_all_case_reasons()`, `_format_metric_value()`.

### Per-case detail view

- New `print_case_detail()` function with:
  - **Single-run mode**: all scores and assertions with diagnostic reasons (e.g., "5 matched, 0 FP, 1 FN").
  - **Comparison mode**: A/B values with deltas and per-run reasons for each metric.
- `--case` CLI option on `report` command. Works alone or with `--compare`.
- Raises `ClickException` with available case names if case not found.

### Post-implementation review fixes

- **Bool/int isinstance bug**: `isinstance(True, (int, float))` returns `True` in Python (bool subclasses int). The per-case comparison delta logic matched booleans as numeric, producing nonsensical deltas. Fixed by adding `not isinstance(val, bool)` guard before the numeric branch.
- **Metric ordering duplication**: Extracted `_ordered_metrics(names)` helper to replace 5 inlined instances of the ordering pattern.
- **Tech debt identified**: `reporting.py` (~430 lines) hand-rolls text formatting that duplicates pydantic-evals' native `report.print(include_reasons=True, baseline=other_report)`. Documented as Phase 3.5 replacement plan in `extractor-agent-plan.md`.

### Files modified

| File | Changes |
|------|---------|
| `src/finding_extractor/eval/runner.py` | `_extract_per_case_results()` captures reasons; `report.print()` gets `include_reasons=True` |
| `src/finding_extractor/eval/reporting.py` | Enhanced `print_comparison()`, new `print_case_detail()`, `METRIC_DISPLAY_ORDER`, helper functions; bool/int bug fix; `_ordered_metrics()` dedup |
| `src/finding_extractor/eval_cli.py` | `--case` option on `report` command |
| `src/finding_extractor/eval/__init__.py` | Re-export `print_case_detail` |
| `tests/test_eval_cli.py` | 7 new tests: `--case` option, reason display, backward compat, enhanced comparison; updated `_make_results_json()` |
| `docs/eval-usage.md` | `--case` flag docs, per-case detail examples, updated run output format |
| `docs/eval-internals.md` | Reporting module description, reason persistence, CLI routing |
| `docs/extractor-agent-plan.md` | Marked Phase 3 completed, documented tech debt, added Phase 3.5 replacement plan |
| `docs/DEV_LOG.md` | This entry |

**Verification:** `task lint` clean, `task test:unit` 300 passed (7 new tests), backward compatible with old results.json format.

## 2026-02-12 — Testing plan Slice 4: split guidance into reusable skill + project doc

Reworked Slice 4 of `docs/testing_plan.md` to follow a two-track testing guidance model:

- reusable pytest best-practice guidance in a local skill
- project-specific testing conventions in `docs/`

Implemented artifacts:

- Added new skill:
  - `.agents/skills/pytest-testing-patterns/SKILL.md`
  - `.agents/skills/pytest-testing-patterns/references/official-pytest-guidance.md`
  - `.agents/skills/pytest-testing-patterns/references/practical-patterns.md`
- Added project-specific testing guide:
  - `docs/testing-practices.md`
- Updated cross-links/discoverability:
  - `docs/testing_plan.md`
  - `README.md`
  - `AGENTS.md`
  - `CLAUDE.md`

Slice status update:
- `docs/testing_plan.md` now marks Slice 4 completed.

## 2026-02-12 — Stage 1 (Backend Phase): Users, patient_id, and correction author schema

Completed Stage 1 from `docs/improving-ui-plan.md` — database foundation for patient linkage and user-attributed corrections.

**Schema Changes (`src/finding_extractor/store.py`):**
- Added `UserRow` table (username PK, name, email, created_at)
- Added `patient_id` column to `ReportRow` (nullable)
- Added `username` FK column to `CorrectionRow` (nullable, references users.username)
- Added `StoredUser` dataclass and mapper function
- Added user management methods: `create_user()` (upsert semantics), `get_user()`, `list_users()`
- Updated `upsert_report()` to accept and update `patient_id` parameter
- Updated `record_correction()` to accept `username` parameter for formal user attribution

**Migration `17d9bf28412d`:**
- Creates `users` table with named FK constraint `fk_corrections_username`
- Adds `patient_id` to reports (nullable)
- Adds `username` FK to corrections (nullable)
- Seeds default user: `talkasab` / Tarik Alkasab / tarik@alkasab.org
- All schema changes are additive and nullable (migration-safe per `docs/schema-migrations.md`)
- Applied successfully with `task db:migrate`, verified with `task db:check`
- Updated `ExtractionStore.EXPECTED_REVISION` to `17d9bf28412d`

**Test Updates:**
- `tests/test_store.py`:
  - Added `test_report_with_patient_id()` — validates patient_id roundtrip and update behavior
  - Added `test_create_and_get_users()` — validates user CRUD operations and upsert semantics
  - Updated `test_record_correction_supports_comment_and_addition()` — validates username FK
- `tests/test_migrations.py`:
  - Updated expected head revision to `17d9bf28412d`
  - Added assertions for `users` table existence
  - Added column checks for `patient_id` (reports) and `username` (corrections)
- All tests pass: 253 unit tests (2 new), 48 UI tests (unchanged)

**Documentation Updates:**
- `docs/persistence-usage.md`:
  - Updated entities section to include users table and relationships
  - Added patient_id parameter to report examples
  - Added user management examples and correction author attribution patterns
  - Updated API reference with new methods and parameters
- `docs/persistence-internals.md`:
  - Updated reports schema with patient_id
  - Updated corrections schema with username FK and backward compatibility note
  - Added users table schema with seeding note
  - Updated Store API Contract with user methods
  - Updated Correction Validation Rules for username FK constraint
  - Updated Migration Policy with 17d9bf28412d details

**Commits:**
- `f094207` — Updated improving-ui-plan.md with resolved decisions
- `4bcda12` — Schema changes + migration 17d9bf28412d
- `18111c4` — Test updates (2 new tests, 2 updated, migration assertions)
- `34867fd` — Documentation updates

Verification:
- `task lint` — passed
- `task test` — 253 passed
- `uv run pytest tests/test_ui.py -v` — 48 passed
- `task db:check` — no drift detected

Next: Stage 2 (API contract updates)

## 2026-02-12 — Stage 2 (Backend Phase): API contract updates

Completed Stage 2 from `docs/improving-ui-plan.md` — extending API contracts with patient linkage and user-attributed corrections.

**API Models (`src/finding_extractor/api_models.py`):**
- Added `UserResponse` model (username, name, email)
- Updated `SubmitReportRequest` with optional `patient_id` field
- Updated `ReportResponse` and `ReportDetailResponse` with optional `patient_id` field
- Updated `CreateCorrectionRequest`:
  - Changed from `created_by: str | None` to `username: str` (required)
  - Added deprecation note for legacy `created_by` field
- Updated `CorrectionResponse`:
  - Added `author: UserResponse | None` for structured user attribution
  - Kept `created_by: str | None` for backward compatibility (always None for new corrections)
- Added mappers:
  - `map_user()` — converts `StoredUser` to `UserResponse`
  - Made `map_correction()` async — fetches user by username and populates `author` field
  - Updated `map_report()` and `map_report_detail()` to include `patient_id`

**API Routes (`src/finding_extractor/api_routes.py`):**
- Added `GET /api/users` endpoint:
  - Returns list of all registered users
  - Logs user count for observability
- Updated `POST /api/reports`:
  - Accepts `patient_id` in request body
  - Passes to `store.upsert_report()`
- Updated `POST /api/extractions/{extraction_id}/corrections`:
  - Validates `username` exists before recording correction
  - Returns `400` if username is invalid
  - Passes `username` to `store.record_correction()`
  - Uses async `map_correction()` to populate author
- Updated `GET /api/extractions/{extraction_id}/corrections`:
  - Uses async `map_correction()` for each correction in list

**Frontend (`extractor-ui/`):**
- Mock handlers (`app.js`):
  - Added `MOCK_DATA.users` with seeded user
  - Added `GET /users` mock handler
  - Updated `MOCK_DATA.report` to include `patient_id: null`
  - Updated mock correction response to include structured `author` object
- Submit form (`app.js`):
  - Added `patientId: ''` to `submitForm` state
  - Updated `submitReport()` to send `patient_id` in request body
- UI (`index.html`):
  - Added Patient ID input field after Source Reference
  - Bound to `submitForm.patientId` with Alpine `x-model`

**Test Updates (`tests/test_api.py`):**
- Added 4 new tests:
  - `test_list_users()` — validates GET /users endpoint
  - `test_submit_report_with_patient_id()` — validates patient_id roundtrip
  - `test_create_correction_with_invalid_username()` — validates 400 response
  - `test_correction_author_structure()` — validates structured author field
- Updated existing tests:
  - `test_create_and_list_corrections()` — uses `username` instead of `created_by`
  - `test_create_update_correction_invalid_index_returns_422()` — includes `username`
  - `test_corrections_not_found()` — includes `username` to test actual 404
- All tests seed users as needed (test DB doesn't inherit migration seeded data)
- Fixed unused variable in `tests/test_store.py`

**Documentation Updates:**
- `docs/api-usage.md`:
  - Updated Quick Start example to include `patient_id`
  - Added `patient_id` to Reports section
  - Added Users section with GET /users endpoint
  - Updated Corrections section with username validation and author structure
- `docs/frontend-usage.md`:
  - Added Patient ID field to Submit Report section
  - Updated Corrections description (username association, future dropdown)
- `docs/frontend-internals.md`:
  - Updated `app.js` structure section with patient_id and username changes
  - Updated Mock Layer section with users endpoint and author structure

**Commits:**
- `4030cf5` — Stage 2: API contract updates

Verification:
- `task lint` — passed (Python; web lint requires eslint)
- `task test` — 257 passed (4 new API tests)
- `uv run pytest tests/test_ui.py -v` — 48 passed (mock mode with new handlers)

Next: Stage 3 (UI improvements for correction workflows and finding-level editing)

## 2026-02-12 — Stage 2 closure fixups (frontend/doc/test coherence)

Addressed post-review drift so Stage 2 backend contracts and extractor UI are aligned.

- `extractor-ui/app.js`:
  - switched correction submit payload from `created_by` to required `username`
  - added username-required validation in `submitCorrection()`
  - updated `submitAndExtract()` to include `patient_id`
  - ensured submit form reset includes `patientId`
- `extractor-ui/index.html`:
  - correction form now uses **Username** field (required)
  - correction list now renders `author` (`name` + `username`) when present
  - preserves legacy fallback display via `created_by`
- `tests/test_ui.py`:
  - updated correction form assertions from "Your name" to "Username"
  - added patient ID field assertion and reset check
  - added disabled-state check when username is blank
- docs sync:
  - `docs/api-usage.md` correction example now uses `username`
  - `docs/frontend-usage.md` and `docs/frontend-internals.md` updated to match real UI behavior

Verification:
- `task test` — passed
- `uv run pytest tests/test_ui.py -v` — passed

## 2026-02-12 — Stage 3: Finding-level inline edit UX

Completed Stage 3 from `docs/improving-ui-plan.md` — per-finding inline correction UI for `update_finding` correction type.

**Frontend Changes (`extractor-ui/`):**
- **index.html** (lines 815-1010, findings section):
  - Enhanced finding presentation with explicit labels for each section (Finding, Location, Attributes, Quote from Report)
  - Added **"Edit this finding"** button at the bottom of each finding card
  - Implemented inline edit form (hidden by default) with fields for:
    - Presence (dropdown: present/absent/possible/indeterminate)
    - Location (body region, specific anatomy, laterality — text inputs)
    - Attributes (JSON object textarea)
    - Comment (optional textarea)
  - Added **Save Changes** and **Cancel** buttons
  - Used Alpine `:id` and `:for` bindings for proper label/input association (e.g., `presence-0`, `location-region-0`)
- **app.js**:
  - Added per-finding edit state: `findingEditState: {}`, `findingEditForms: {}`
  - Added `startFindingEdit(fIdx, finding)` — opens inline form, prefills with current finding values, converts attributes array to JSON object
  - Added `cancelFindingEdit(fIdx)` — closes form without submitting
  - Added `submitFindingEdit(fIdx)` — validates attributes JSON, constructs `update_finding` correction payload with `target_finding_index`, submits to API, reloads corrections
  - Mock handler already supported generic corrections, no updates needed

**Test Updates:**
- `tests/test_ui.py`:
  - Added new `TestFindingEdit` class with 5 tests:
    - `test_edit_button_present_for_each_finding` — button visibility
    - `test_edit_form_opens_on_click` — form shows with all expected fields
    - `test_edit_form_prefills_current_values` — values from mock finding are loaded
    - `test_cancel_closes_edit_form` — cancel hides form without submitting
    - `test_save_changes_submits_and_closes_form` — submit closes form successfully
  - All tests use mock mode, no backend required
  - Total UI tests: 54 (49 existing + 5 new)

**Documentation Updates:**
- `docs/frontend-usage.md`:
  - Added detailed **Inline Finding Edits** section under Extraction Detail
  - Documented editable fields, actions (Save Changes/Cancel), and prefill behavior
  - Clarified global comment-only corrections coexist with per-finding edits
- `docs/frontend-internals.md`:
  - Added **Finding-Level Edit State** section with state structure, methods, and payload example
  - Updated mock layer note to mention `update_finding` support
  - Updated test classes list to include `TestFindingEdit`

**Stage 3 Contract Alignment Fix (2026-02-12):**

After initial Stage 3 implementation, technical review identified a critical API contract mismatch: `submitFindingEdit()` was sending nested objects inside `attribute_overrides`, but the backend requires `attribute_overrides: dict[str, str] | None` (flat string map only). Mock-mode UI tests passed, hiding the bug that would cause real API calls to fail with Pydantic validation errors.

**Fix Applied:**
- **extractor-ui/app.js** (`submitFindingEdit()`):
  - Changed from malformed `attribute_overrides: { presence: '...', location: {...}, ... }` (nested objects)
  - To correct `proposed_finding` structure with complete `ExtractedFinding` object matching backend schema
  - Preserves `finding_name` and `report_text` from original, applies edited values for `presence`, `location`, and `attributes`
  - Converts attributes from JSON textarea to array of `{key, value}` pairs as backend expects
- **tests/test_api.py**:
  - Added `test_update_finding_with_proposed_finding()` — backend test verifying `update_finding` submissions with `proposed_finding` are accepted
  - Guards against reintroduction of nested `attribute_overrides` bug
- **docs/frontend-internals.md**:
  - Updated payload example to show correct `proposed_finding` structure instead of malformed `attribute_overrides`
  - Added note about API contract compliance
- **docs/improving-ui-plan.md**:
  - Added Stage 3 contract alignment fix section with verification checkboxes
  - Marked Stage 3 as merge-ready

**Commits:**
- (pending) — Stage 3 implementation: finding-level inline edit UX + contract alignment fix

Verification (after fix):
- `task lint` — Python passed (eslint unavailable)
- `task test` — 258 passed (+1 new backend test for contract validation)
- `uv run pytest tests/test_ui.py -v` — 54 passed (unchanged, 5 new tests from initial Stage 3)

**Stage 3 confirmed merge-ready** ✅

Next: Stage 4 (user dropdown selector UX improvement)

## 2026-02-12 — Stage 4: User dropdown selector UX

Completed Stage 4 from `docs/improving-ui-plan.md` — replaced free-text username input with dropdown selector backed by `GET /api/users`.

**Frontend Changes (`extractor-ui/`):**
- **app.js**:
  - Added users state: `users` (array), `usersLoading` (boolean), `usersError` (string | null)
  - Changed `correctionForm.username` initial value from `'talkasab'` to empty string
  - Added `loadUsers()` method called from `loadExtraction()`:
    - Fetches users from `/users` endpoint
    - Defaults selection to `talkasab` when present, else first user
    - Sets `usersError` and empty `username` on failure
  - Updated `submitFindingEdit()` disabled logic to respect `usersLoading`, `usersError`, and empty `users` list
- **index.html**:
  - Replaced username text input with Flowbite select element (`#username-select`)
  - Select populates from `users` array using Alpine `x-for` template
  - Shows loading state, error message, and empty-list warning with appropriate disabled/error styling
  - Updated "Submit Comment" button disabled logic to gate on users state
  - Updated "Save Changes" button (finding-level edits) disabled logic to gate on users state

**Test Updates (`tests/test_ui.py`):**
- Updated existing `TestCorrections` class tests to work with select instead of textbox:
  - `test_correction_form_present` — checks for `select#username-select` visibility
  - `test_submit_button_disabled_without_username` — simplified (empty selection not possible by design)
  - `test_submit_correction_clears_form` — verifies username persists after submit (pre-selected behavior)
- Added new `TestUserDropdown` class with 4 tests:
  - `test_username_selector_populated_from_users_api` — verifies dropdown populated and talkasab selected
  - `test_default_selection_prefers_talkasab` — confirms default selection logic
  - `test_correction_submit_respects_user_gating` — validates submit enabled when user selected
  - `test_finding_edit_respects_user_gating` — validates finding edit submit respects same gating

**Documentation Updates:**
- `docs/frontend-usage.md`: Updated corrections section to describe dropdown behavior, default selection, and error/disabled states
- `docs/frontend-internals.md`:
  - Updated app.js structure diagram with users state
  - Added "User Loading and Selection" section documenting `loadUsers()` logic and submit gating
  - Updated test classes list to include `TestUserDropdown`
- `docs/improving-ui-plan.md`: Marked Stage 4 complete with all checklists and verification results

**Verification:**
- `task lint` — passed (Python + web + JSON + TOML + DB checks)
- `task test` — 258 passed (unit tests unchanged)
- `uv run pytest tests/test_ui.py -v` — 58 passed (+4 new tests for user dropdown)
- Runtime smoke test — `GET /api/users` returns talkasab, dropdown functional in browser

**All stages 0-4 complete** 🎉 — patient linkage, user attribution, finding-level edits, and user dropdown UX all working and merge-ready.

## 2026-02-13 — Post-Stage 4 UI improvement fixes

Fixed three issues identified in Stage 4 code review to make the feature branch merge-ready.

**Fix #1: Removed Alpine runtime warnings in finding edit UI**
- Changed edit form from `x-show` (hide/show) to `x-if` (conditional DOM rendering)
- Prevents Alpine from evaluating `x-model` bindings on undefined `findingEditForms[fIdx]` state
- No console warnings when loading extraction detail or toggling finding edits

**Fix #2: Made finding edit payload always valid against backend schema**
- Changed `body_region` and `laterality` from free-text inputs to select dropdowns with enum values
- Options match backend `FindingLocation` literals (chest, abdomen, pelvis, head, neck, spine, upper/lower extremity, breast)
- Fixed location construction to send `location: null` when all fields empty (not `{body_region: null}`)
- Backend requires `body_region` to be valid literal (not null) if location object exists

**Fix #3: Eliminated N+1 user lookups when listing corrections**
- `GET /api/extractions/{id}/corrections` now batches user lookup with single `list_users()` call
- Built user map passed to new `map_correction_with_users()` function
- Reduced queries from (1 + N) to 2 constant queries
- Response contract unchanged (author object + legacy created_by field preserved)

**Files changed:**
- `extractor-ui/index.html` — x-if template, select dropdowns for location enums
- `extractor-ui/app.js` — location null logic when fields empty
- `src/finding_extractor/api_routes.py` — batch user lookup in corrections list
- `src/finding_extractor/api_models.py` — added `map_correction_with_users()` with pre-fetched map

**Verification:**
- 258 unit tests pass (unchanged)
- 58 UI tests pass (unchanged)
- All lint checks pass
- No console warnings on extraction detail interactions
- Finding edit submit succeeds with valid payloads
- No breaking changes, no new dependencies

See `docs/ui-improvement-fixes.md` for detailed fix specifications.

## 2026-02-12 — Testing plan Slice 3: shared runtime logging patch helper

Executed Slice 3 from `docs/testing_plan.md` by centralizing startup logging monkeypatch patterns.

- Added `runtime_logging_spy` fixture in `tests/conftest.py`:
  - patches `configure_logfire(...)` and `setup_logging(...)` for a target module
  - captures call metadata (`runtime`, `enabled_override`, `fastapi_app`, settings, `include_logfire_processor`)
- Migrated startup wiring tests to use the shared helper in:
  - `tests/test_api.py`
  - `tests/test_cli.py`
  - `tests/test_batch_cli.py`
  - `tests/test_eval_cli.py`
  - `tests/test_tasks.py`
- Kept assertions explicit at each callsite.
- Updated `docs/testing_plan.md` to reflect:
  - Slice 3 completed
  - Slice 4 next

Verification:
- `uv run pytest tests/test_api.py tests/test_cli.py tests/test_batch_cli.py tests/test_eval_cli.py tests/test_tasks.py -q`
- `task lint`
- `task test`

## 2026-02-12 — Testing plan Slice 2: shared async store factory

Executed Slice 2 from `docs/testing_plan.md` by centralizing async store setup/teardown for backend tests.

- Added `store_factory` fixture in `tests/conftest.py`:
  - returns an async context manager that initializes and closes `ExtractionStore`.
- Migrated duplicated per-module store setup/teardown wrappers to use `store_factory` in:
  - `tests/test_store.py`
  - `tests/test_api.py`
  - `tests/test_tasks.py`
- Updated `docs/testing_plan.md` to reflect:
  - Slice 2 completed
  - Slice 3 next

Verification:
- `uv run pytest tests/test_store.py tests/test_api.py tests/test_tasks.py -q`
- `task lint`
- `task test`

## 2026-02-12 — Testing plan Slice 1: shared CLI runner fixture

Executed Slice 1 from `docs/testing_plan.md` and standardized CLI test runner setup via a shared fixture.

- Added `cli_runner` fixture in `tests/conftest.py`.
- Replaced direct `CliRunner()` construction in:
  - `tests/test_cli.py`
  - `tests/test_batch_cli.py`
  - `tests/test_eval_cli.py`
- Removed local `runner` fixture duplication from eval CLI tests.
- Updated `docs/testing_plan.md` to reflect:
  - Slice 1 completed
  - Slice 2 next

Verification:
- `uv run pytest tests/test_cli.py tests/test_batch_cli.py tests/test_eval_cli.py -q`
- `task lint`
- `task test`

## 2026-02-12 — Stage 2 Phase 2.5: Matching Algorithm Improvements

Fixed a disambiguation problem where duplicate-name findings (renal calculus ×2, spinal degenerative change ×2, etc.) with identical `report_text` produced identical Jaccard scores, making pairing random and cascading errors into Location, Attribute, and Presence evaluators.

### Matching improvements

- **Tokenization hardening**: Replaced `text.lower().split()` with regex `\w+` word extraction. Strips punctuation (`"kidney."` → `"kidney"`, `"4–5"` → `{"4", "5"}`).
- **Location-aware scoring**: `_location_bonus()` adds up to +0.15 for matching body_region (+0.05), laterality (+0.05), and specific_anatomy token overlap (+0.05).
- **Attribute-aware scoring**: `_attribute_bonus()` adds up to +0.03 for matching key-value attribute pairs.
- Bonuses are tiebreakers only — the default threshold (0.3) is unchanged.

### Evaluator diagnostic reasons

Folded in deferred item #5 from Phase 1.5: all finding-based evaluators now return `EvaluationReason` with count strings:
- `PresenceClassificationEvaluator` → `"5/6 correct"`
- `LocationEvaluator` → `"3/4 correct"` for body_region and laterality
- `AttributeEvaluator` → `"5/7 matched"` for precision and recall

### Diagnostic tests

- `TestSelfMatchDiagnostics`: Loads comprehensive dataset, self-matches each case, verifies correct pairing of duplicate-name findings by laterality and anatomy.
- `TestDisambiguation`: Constructs two findings with same name + text + different laterality/anatomy, verifies correct pairing.
- `TestLocationBonus` and `TestAttributeBonus`: Unit tests for the bonus helper functions.

### Files modified/created

| File | Changes |
|------|---------|
| `src/finding_extractor/eval/matching.py` | Regex tokenization, `_location_bonus()`, `_attribute_bonus()`, wired into scoring loop |
| `src/finding_extractor/eval/evaluators.py` | `EvaluationReason` for Presence, Location, Attribute evaluators |
| `tests/test_eval_matching.py` | 18 new tests: disambiguation, self-match diagnostics, bonus helpers, tokenization |
| `tests/test_eval_evaluators.py` | Updated for `EvaluationReason` returns, reason string assertions |
| `docs/extractor-agent-plan.md` | Marked Phase 2.5 completed, marked deferred item #5 done |
| `docs/eval-internals.md` | Updated matching algorithm section with bonuses and constants table |
| `docs/DEV_LOG.md` | This entry |

### Code review revisions (same session)
- **Removed dead guard** in `_attribute_bonus()`: the `total == 0` check after `if not expected.attributes or not actual.attributes` was unreachable.
- **Precomputed anatomy tokens**: `_location_bonus()` was calling `tokenize()` on `specific_anatomy` inside the O(n*m) loop. Extracted `_anatomy_tokens()` precomputation to match the pattern used for main Jaccard tokens, passing precomputed sets into `_location_bonus()`.
- **Tests use public API**: Rewrote `TestLocationBonus` and `TestAttributeBonus` to exercise bonus behavior through `match_findings()` instead of importing private `_location_bonus`/`_attribute_bonus` directly. Tests are now resilient to internal refactoring.
- **Documented circular scoring limitation**: Added "Known Limitation: Circular Scoring" section to `docs/eval-internals.md` explaining the feedback loop between matcher bonuses and evaluator scoring, why it's the correct trade-off, and the theoretical blind spot (complementary laterality swaps).
- **Documented new ideas**: Added three future improvement items to `docs/extractor-agent-plan.md`: matching confidence meta-evaluator, evaluator coverage of unmatched findings, and cross-validation for circular scoring detection.

**Verification:** `task lint` clean, `task test:unit` 298 passed (18 new tests).

## 2026-02-12 — Stage 2 Phase 2: Dataset Expansion + Comparison Tooling

Added `import-baseline` and `report` CLI subcommands, built the comprehensive dataset, and wired into Taskfile.

### New CLI subcommands

- **`import-baseline`**: Imports reviewed batch extraction results (`*.extracted.json`) as ground truth eval cases. Supports `--glob`, `--output-suffix`, `--append/--no-append`, `--source-label`, `--model-filter`. Strips `_validation` and `_storage` keys, infers metadata from `exam_info`, deduplicates by case name on append.
- **`report`**: Views results from a previous eval run. Shows latest run by default, supports `--compare` for side-by-side comparison with colored delta arrows (green=improvement, red=regression).

### New modules

- `src/finding_extractor/eval/reporting.py` — `load_run_results()`, `find_latest_run()`, `print_run_summary()`, `print_comparison()`.
- `src/finding_extractor/eval/datasets.py` — added `import_baseline_cases()`, `save_dataset()`, `_infer_metadata()`, `_case_name_from_path()`.

### Comprehensive dataset

- 9 cases from `sample_data/example2/` covering CT abdomen (4), MR brain (1), US abdomen (1), XR chest (2), XR shoulder (1).
- Generated via batch extraction (`openai:gpt-5-mini`, medium reasoning) then imported with `import-baseline`.
- CT chest case excluded (consistently fails verbatim validation after max retries).
- Stored at `evals/datasets/comprehensive.yaml`.

### Taskfile

- Added `eval:comprehensive` task for running the 9-case comprehensive dataset.
- Added `tests/test_eval_datasets.py` to `test:unit` target.

### Tests

- `tests/test_eval_datasets.py` (new): 17 tests covering `import_baseline_cases()` edge cases (basic, strip keys, metadata inference, custom glob/suffix, model filter, parse errors, empty dir) and `save_dataset()` (by name, by path, round-trip).
- `tests/test_eval_cli.py`: added `TestImportBaselineCli` (5 tests) and `TestReportCli` (6 tests).

### Files modified/created

| File | Changes |
|------|---------|
| `src/finding_extractor/eval_cli.py` | Added `import-baseline` and `report` subcommands |
| `src/finding_extractor/eval/datasets.py` | Added `import_baseline_cases()`, `save_dataset()` |
| `src/finding_extractor/eval/reporting.py` | **New**: run result loading, summary printing, comparison |
| `src/finding_extractor/eval/__init__.py` | Re-exported new public names |
| `evals/datasets/comprehensive.yaml` | **New**: 9-case comprehensive dataset |
| `Taskfile.yml` | Added `eval:comprehensive` task, `test_eval_datasets.py` to test:unit |
| `tests/test_eval_cli.py` | Tests for import-baseline and report subcommands |
| `tests/test_eval_datasets.py` | **New**: unit tests for dataset import logic |
| `docs/extractor-agent-plan.md` | Marked Phase 2 completed |
| `docs/DEV_LOG.md` | This entry |
| `docs/eval-usage.md` | import-baseline + report CLI docs, dataset tiers, Taskfile commands |
| `docs/eval-internals.md` | Module map, reporting architecture, dataset flow |

**Verification:** `task lint` clean, `task test:unit` passed.

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
