# Extractor Agent Improvement Plan

Date: 2026-02-10

## Purpose

Define a staged, low-risk roadmap to improve extraction quality, reliability, model portability (including Ollama/local models), and progression toward coded observations (OIFM + anatomic location codes).

## Principles

1. Fix correctness and observability before architecture expansion.
2. Use evaluation gates between stages; do not proceed on subjective quality alone.
3. Keep transactional app data in SQLite; use DuckDB where analytical/index workloads fit better.
4. Keep extraction and coding decoupled at first (extract facts first, code second).
5. Prefer stable public dependencies (`findingmodel`, `anatomic-locations`) over internal-only packages unless explicitly vendored/pinned.

## Current Gaps (Baseline)

1. Reasoning override semantics are inconsistent (`none` can be ineffective for some providers).
2. Prompt is large and static; examples are hard-coded and always inlined.
3. No run-time event stream for progress/status in CLI/web.
4. No eval harness tied to prompt/example changes.
5. Local-model structured-output reliability is not yet hardened (fallback output modes not implemented).
6. No Ollama discovery in model catalog and no model-capability profiling.
7. Corrections history is not yet mined as a first-class eval/example signal.
8. No fast replay/comparison workflow for same-report multi-extraction iteration.
9. Cost/token visibility is not yet first-class in persisted run metadata.
10. No coded-observation pipeline yet (OIFM/anatomic coding is not separated as a first-class stage).

## Staged Roadmap

## Stage 0: Correctness and Contracts (COMPLETED 2026-02-11)

Objective: eliminate correctness footguns before adding complexity.

Scope:
1. Fix reasoning override behavior so `reasoning="none"` is always honored.
2. Add explicit reasoning input validation in Python/API paths.
3. Add model-family reasoning compatibility validation:
   1. enforce per-model allowed levels (for example, GPT-5 vs GPT-5.1 vs GPT-5.2)
   2. include support for new levels such as `xhigh` when available
   3. reject unsupported model+reasoning combinations early in API/CLI
4. Ensure OpenAI `reasoning="none"` is sent explicitly when supported by the selected model; do not silently drop to defaults.
5. Add integration tests that assert effective provider settings at run time.
6. Add model setting resolution unit tests for all provider prefixes in use.
7. Promote usage accounting to a required contract:
   1. capture tokens/usage from agent run results where provider supports it
   2. persist usage in extraction/job metadata with nullable fields for unsupported providers

Deliverables (all completed):
1. `ReasoningLevel` type and `VALID_REASONING_LEVELS` derived from it via `get_args()`.
2. `validate_reasoning()` and `validate_reasoning_for_model()` with clear `ValueError` messages.
3. `PROVIDER_SUPPORTED_REASONING` compatibility matrix (Ollama: `none` only; others: all levels).
4. All three providers now send explicit settings for `reasoning="none"` (OpenAI: `reasoning_effort="none"`, Google: `thinking_level="NONE"`, Anthropic: `{"type": "disabled"}`).
5. `ExtractionUsage` model and `ExtractionResult` return type from `extract_findings()`.
6. Usage columns added to `extractions` table via Alembic migration `7537480089ba`.
7. Usage surfaced in API responses (`ExtractionSummaryResponse`, `ExtractionDetailResponse`) and CLI output.
8. `duration_ms` captured via `time.monotonic()` for wall-clock extraction timing.
9. 422 errors for invalid reasoning in API; fail-fast in CLI; defense-in-depth in worker.
10. Comprehensive test coverage across `test_extraction.py`, `test_api.py`, `test_cli.py`.

Exit criteria (all met):
1. `--reasoning none` and API equivalent verified for OpenAI, Anthropic, Google, Ollama.
2. CI includes new tests and passes (142+ tests).
3. Usage/cost-related metadata is available for model comparison dashboards.

## Stage 1: Status Messages for In-Flight Progress (COMPLETED 2026-02-11)

Objective: make extraction progress visible to API pollers and CLI users without new infrastructure.

Scope:
1. Add `status_message` column to `jobs` table for human-readable in-flight progress.
2. Worker updates `status_message` at each extraction phase boundary (retrieving report, validating model, extracting, validating, saving).
3. CLI emits equivalent progress to stderr via `click.echo(..., err=True)` during synchronous extraction.
4. Usage/timing per run already captured in Stage 0.

Implementation notes:
1. No new tables, no SSE, no events infrastructure — polling `GET /api/jobs/{job_id}` is sufficient for current needs.
2. `mark_job_running/completed/failed` set bookend status messages automatically.

Exit criteria:
1. API pollers see human-readable progress during extraction via `status_message` field in job response.
2. CLI shows progress on stderr during synchronous extraction.

## Stage 1.5: Agent Status Callback (COMPLETED 2026-02-11)

Objective: let the extraction agent report progress from within `extract_findings()` via an injected async callback, replacing the silent black-box LLM call with visible status updates.

Scope:
1. Add `status_callback` field to `ExtractorDeps` (optional, default `None`).
2. Add `_emit_status()` helper to invoke the callback when present.
3. Emit status before model call ("Calling model..."), on verbatim validation retries ("Retrying: verbatim validation failed (N error(s))"), and after completion ("Model call complete, processing results").
4. Worker passes a callback that writes to the DB via `store.update_job_status_message()`.
5. CLI passes a callback that prints to stderr via `click.echo(..., err=True)`.
6. Make the output validator async to support status emission on retries.

Exit criteria:
1. API pollers see "Calling model..." and retry messages during the LLM call, not just silence.
2. CLI shows agent-internal progress on stderr during synchronous extraction.
3. Tests verify callback invocation and message propagation in both worker and CLI paths.

## Stage 2: Evaluation Harness and Quality Gates

Objective: make changes measurable and regression-safe.

### Phase 1: Minimal Viable Eval (COMPLETED 2026-02-11)

Scope:
1. Built eval subpackage (`src/finding_extractor/eval/`) with models, matching, evaluators, task adapter, runner, and datasets helper.
2. Implemented 6 custom evaluators covering all scoring dimensions:
   1. Finding detection (precision/recall/F1) via Jaccard token similarity matching
   2. Presence classification accuracy on matched findings
   3. Location accuracy (body_region, laterality)
   4. Attribute extraction precision/recall
   5. Verbatim quote exactness (reuses `check_verbatim()` from agent)
   6. Non-finding text classification accuracy
3. Created smoke dataset (2 cases from existing few-shot examples) stored as version-controlled YAML at `evals/datasets/smoke.yaml`.
4. Added `finding-extractor-eval` CLI with `run` subcommand and threshold checking.
5. Added `task eval:smoke` Taskfile command for CI quality gates.
6. Full test coverage: 66 tests across matching, evaluators, and CLI.

Docs: `docs/eval-usage.md` (user guide), `docs/eval-internals.md` (developer guide).

### Immediate follow-up: Per-case retries via pydantic-evals (COMPLETED 2026-02-12)

Phase 1 shipped without per-case retry support. Wired pydantic-evals' native `retry_task` parameter (backed by tenacity) with `stop_after_attempt` + `wait_exponential`.
1. `_build_retry_config()` in `runner.py` builds the tenacity config dict.
2. `--retries` CLI option and `eval_retries` config setting (`IPL_EVAL_RETRIES`, default 1).
3. `retries` field on `EvalRunConfig` dataclass.

### Phase 1.5: Deeper pydantic-evals integration (COMPLETED 2026-02-12)

Scope:
1. `verbatim_pass` now returns `bool` via `EvaluationReason` → routes to `case.assertions` instead of `case.scores`.
2. `EvaluationReason` used in `FindingDetectionEvaluator` (match/FP/FN counts) and `VerbatimQuoteEvaluator` (verbatim counts).
3. Baseline comparison (`report.print(baseline=other_report)`) deferred to Phase 2 — requires loading a previous report object, not just JSON.
4. `NonFindingClassificationEvaluator` reuses `tokenize()`/`jaccard_similarity()` from `matching.py`.
5. `_extract_averages()` computes per-assertion pass rates from per-case data (since `report.averages().assertions` is a single aggregate float, not per-metric).

Review revisions (same session):
- Reverted `_match_or_default()` shared helper — the inline pattern (3 lines per evaluator) is clearer, type-safe, and avoids a positional-return-tuple API. Each evaluator keeps its own `expected = ctx.expected_output` / `if expected is None: return {defaults}` / `result = match_findings(...)` pattern.
- Promoted `_tokenize()`/`_jaccard_similarity()` to public API (`tokenize()`/`jaccard_similarity()`) since they're now imported across module boundaries.

### Phase 2: Dataset Expansion + Comparison Tooling (COMPLETED 2026-02-12)

Scope:
1. `import-baseline` subcommand to promote reviewed `*.extracted.json` files to ground truth eval cases.
2. `report` subcommand to view run summaries and `--compare` to diff two eval runs (model A vs model B).
3. `comprehensive` dataset (10 cases from `sample_data/example2/`) covering CT, MR, US, XR across multiple body regions.
4. `eval:comprehensive` Taskfile command for running the full diversity check.
5. Unit tests for `import_baseline_cases()`, `save_dataset()`, and both new CLI subcommands.

Deferred:
- Correction mining into datasets — no corrections exist yet. Deferred until the correction workflow is actively used.
- Expansion to 20-50 cases — requires additional ground truth data beyond the current 10 sample reports.

### Phase 2.5: Matching Algorithm Improvements (Planned)

The current Jaccard token similarity matching is simple and dependency-free but may not scale well as datasets grow. Consider:
1. **LLM-as-judge**: Use pydantic-evals' built-in `LLMJudge` evaluator for semantic similarity scoring — more accurate for paraphrase-heavy findings but adds latency and cost per eval run.
2. **Embedding similarity**: Pre-compute embeddings for finding names + report text and use cosine similarity — faster than LLM-as-judge at scale, requires an embedding model dependency.
3. Evaluate whether the current Jaccard approach produces incorrect matches/misses on the expanded dataset before investing in alternatives.

### Phase 3: Advanced Reporting (Planned)

Scope:
1. Per-case diff visualization.
2. Historical trend tracking across runs.
3. CI dashboard integration.
4. **Logfire integration**: Add traces showing why an eval case failed (exact tool calls the agent made, token usage, retry paths) — builds on existing `observability.py` infrastructure.

Exit criteria (Stage 2 overall):
1. Any prompt/example/model-policy change has before/after scores.
2. Regression thresholds are enforced in CI.
3. Corrections-derived cases are included in at least one maintained regression dataset.

## Stage 3: Prompt Refactor and Output Reliability

Objective: improve extraction consistency while reducing token load.

Scope:
1. Split INSTRUCTIONS constant into:
   1. stable policy block
   2. concise task block
   3. dynamically selected examples
   Note: The INSTRUCTIONS constant is currently a large f-string in `agent.py`. Refactor early in this stage — move to a template file or cleaner builder function before adding dynamic examples, to avoid the prompt becoming unmanageable.
2. Tighten schema-driven output guidance and conflict rules (e.g., impression restatements vs findings duplication).
3. Add deterministic preprocessing:
   1. section labeling
   2. report normalization
   3. quote span tracking hints
4. Improve verbatim validation to prefer span/offset checks over normalized global substring checks.
5. Add partial-success policy for validation failures:
   1. strict mode: fail job when critical validation fails
   2. lenient mode: persist valid findings, drop invalid spans/findings, attach warnings
   3. include machine-readable warning payload with dropped item counts and reasons
   4. terminal status should become `completed_with_warnings`, not `failed`, in lenient mode
6. Move local-model output reliability into this stage:
   1. implement output-mode fallback policy by model capability:
      1. Tool Output (preferred)
      2. Native Output (when supported and safe)
      3. Prompted Output (last-resort fallback)
   2. add per-model capability tests for representative Ollama models (`qwen3`, `gpt-oss`, `llama3.3`)
   3. require structured-output pass-rate threshold before marking a local model profile as supported

Exit criteria:
1. Prompt token size reduced materially from current baseline.
2. Eval quality is same or better across cloud and local models.
3. Partial-success behavior is deterministic and test-covered in both strict and lenient modes.
4. Local-model structured-output fallback path is implemented and validated on supported profiles.

## Stage 3.5: Baseline Coding Bridge (Early OIFM/Location Coverage)

Objective: provide immediate partial coded output for EFL/viewer compatibility before full semantic coding.

Scope:
1. Add lightweight post-extraction coding pass using deterministic lookup first:
   1. exact finding-name match against `findingmodel` index
   2. synonym match against `findingmodel` index
   3. optional curated alias dictionary for common local naming variants
2. Add lightweight anatomic mapping pass:
   1. body_region + specific_anatomy to best-fit RID candidate via `anatomic-locations`
   2. preserve laterality when variants are available
3. Mark all Stage 3.5 coding as provisional:
   1. `coding_method`: `exact` | `synonym` | `alias`
   2. confidence default low/medium (never high in this stage)
   3. include unresolved items list
4. Keep coding additive and non-blocking:
   1. extraction remains source of truth
   2. coding failure must not fail extraction job

Exit criteria:
1. A meaningful subset of findings in standard reports has OIFM and location IDs.
2. Viewer/EFL paths can consume partially coded outputs.
3. Unmapped findings are explicitly reported for later Stage 7 semantic coding.

## Stage 4A: File-Based Example Management (Lightweight First)

Objective: replace hard-coded examples with low-complexity, metadata-driven selection before adding new storage infrastructure.

Scope:
1. Move examples from Python module constants into JSON/YAML catalog files.
2. Add metadata tags per example (modality, body_region, report length bucket, key patterns).
3. Implement deterministic selector (tag matching + small diversity rules) to choose 1-3 examples.
4. Add curator workflow for adding/editing examples without code edits.

Exit criteria:
1. No hard-coded examples in agent module path.
2. Example selection is deterministic/reproducible with audit logging.
3. Eval score improves or prompt size decreases without quality loss.

## Stage 4B: Optional DuckDB Example Retrieval (Advanced)

Objective: add retrieval-backed example selection only if Stage 4A is insufficient.

Trigger to execute Stage 4B:
1. Stage 4A cannot meet quality/latency targets.
2. Example set growth makes file-based curation/querying operationally difficult.

Why DuckDB here:
1. Example retrieval is analytical/index-like workload, not OLTP.
2. Good fit for vector + metadata filtering and offline curation workflows.

Scope:
1. Add DuckDB example catalog with metadata and optional embeddings.
2. Add retrieval policy that combines metadata filtering and semantic similarity.
3. Keep Stage 4A path as fallback for operational resilience.

Dependency recommendation:
1. Prefer public `findingmodel`/`anatomic-locations` packages.
2. If reusing `oidm-common` patterns, pin exact revision or vendor code since `oidm-common` is internal-only.

Exit criteria:
1. Retrieval path is measurably better than Stage 4A on eval metrics, or clearly lower maintenance burden.
2. Operational fallback to Stage 4A remains available.

## Stage 5: Multi-Model Expansion and Ollama Readiness

Objective: support more local models safely and transparently after output reliability is in place.

Scope:
1. Refactor `_build_*_settings` functions in `agent.py` into a separate `providers.py` module. These functions are growing long and will become a maintenance burden as more providers/parameters are added. Do this early in Stage 5.
2. Add Ollama model discovery (`/api/tags`) into `/api/models`.
3. Add model capability registry:
   1. tool-calling support
   2. structured output mode support
   3. thinking support/options
   4. context window
4. Add model profile presets:
   1. cloud-high-quality
   2. cloud-low-cost
   3. local-balanced (`qwen3:8b/14b`)
   4. local-high-quality (`gpt-oss:120b`)

Exit criteria:
1. `/api/models` includes local Ollama inventory.
2. Each model has known-safe profile and documented capability contract.
3. Eval dashboard reports per-model performance and cost/latency.

## Stage 6: Report Chunking and Sub-Agent Pipeline (Conditional)

Objective: improve long-report robustness only when justified by measured failure/latency patterns.

Execute Stage 6 only if:
1. Stage 2/5 metrics show material long-report failure/quality degradation.
2. Cost/latency tradeoff justifies added orchestration complexity.

Scope:
1. Add deterministic section/chunk splitter (Findings, Impression, Technique, etc.).
2. Introduce map-reduce extraction:
   1. chunk extractor agent (facts only)
   2. merge/dedupe normalizer agent
   3. final schema validator/retry pass
3. Route strategy:
   1. single-pass for short reports + high-capability models
   2. chunked pipeline for long reports and/or constrained local models

Exit criteria:
1. Long-report failure rate decreases.
2. Chunking complexity is justified by measured quality/latency gains.

## Stage 7: Coded Observation Planning (OIFM + Anatomic Locations)

Objective: move from baseline lookup coding to robust semantic coding without destabilizing extraction.

Scope:
1. Define a new post-extraction coding stage (separate from extraction agent):
   1. input: extracted finding facts + evidence spans
   2. output: ranked OIFM candidates and ranked anatomic location candidates
2. Integrate `findingmodel` index for OIFM candidate search and metadata.
3. Integrate `anatomic-locations` index for location IDs, hierarchy, laterality variants, and external codes.
4. Extend persistence with optional coding payload:
   1. top candidate
   2. alternates
   3. confidence
   4. rationale/evidence span pointers
5. Add review workflow:
   1. human accepts/edits/rejects coding
   2. corrections feed future evals and example curation

Exit criteria:
1. Extraction output remains backward compatible.
2. Coding results are available as additive fields with confidence and provenance.
3. Human review loop exists for low-confidence mappings.

## Stage 8: Exam Finding List Output Contract

Objective: deliver IPL/EFL-ready observation records with stable contracts.

Scope:
1. Finalize observation schema:
   1. finding statement
   2. presence
   3. OIFM code/id
   4. anatomic location id(s)
   5. laterality
   6. supporting quote spans
   7. uncertainty/confidence
2. Add deterministic conflict handling:
   1. mutually exclusive findings
   2. impression-vs-findings contradictions
3. Add export adapters for downstream consumer formats.

Exit criteria:
1. End-to-end generation of coded exam finding list from raw report.
2. Schema versioned and documented with migration notes.

## Stage 9: Production Hardening

Objective: operational readiness.

Scope:
1. Add SLOs and monitoring dashboards:
   1. success rate
   2. latency percentiles
   3. retry rates
   4. model-specific failure classes
2. Add canary rollout for prompt/example/model changes.
3. Add data governance checks for PHI handling in logs/events/examples.

Exit criteria:
1. Controlled rollout process exists for all agent changes.
2. Runbook exists for model outage/fallback behavior.

## Suggested Implementation Order and Milestones

1. Milestone A (Weeks 1-2): Stage 0 + Stage 1.
2. Milestone B (Weeks 3-4): Stage 2 + Stage 3.
3. Milestone C (Weeks 5-6): Stage 3.5 + Stage 4A.
4. Milestone D (Weeks 7-9): Stage 5 + Stage 4B (optional, if triggered).
5. Milestone E (Weeks 10-12): Stage 6 (conditional, if triggered).
6. Milestone F (Weeks 13-15): Stage 7.
7. Milestone G (Weeks 16+): Stage 8 + Stage 9.

## Architectural Decisions to Confirm Early

1. Keep SQLite as system-of-record for reports/jobs/extractions.
2. Prefer file-based example management first; add DuckDB only if Stage 4B trigger conditions are met.
3. Keep extraction and coding as separate stages and separate APIs internally.
4. Use polling with `status_message` field for progress visibility; add SSE/WebSocket only if polling latency becomes a UX problem.
5. Use public `findingmodel` and `anatomic-locations` packages first; only adopt internal `oidm-common` with explicit pinning strategy.
6. Pin `pydantic-evals` to a stable version. The eval harness (Stage 2) depends on it for dataset serialization, evaluator protocol, and run reporting. Breaking changes in `pydantic-evals` could invalidate historical benchmarks and require dataset migration. Pin and upgrade deliberately.

## External References Used

1. PydanticAI agents and streaming events:
   1. https://ai.pydantic.dev/agents/
2. PydanticAI structured output modes:
   1. https://ai.pydantic.dev/output/
3. Pydantic Evals dataset management:
   1. https://ai.pydantic.dev/evals/how-to/dataset-management/
4. Open Imaging FindingModel repository:
   1. https://github.com/openimagingdata/findingmodel
5. FindingModel configuration and model override patterns:
   1. https://raw.githubusercontent.com/openimagingdata/findingmodel/main/docs/configuration.md
6. Anatomic location index usage and coding support:
   1. https://raw.githubusercontent.com/openimagingdata/findingmodel/main/docs/anatomic-locations.md
7. OIFM-capable model/index package overview:
   1. https://raw.githubusercontent.com/openimagingdata/findingmodel/main/packages/findingmodel/README.md
8. Ollama model pages for local-model rollout assumptions:
   1. https://ollama.com/library/gpt-oss
   2. https://ollama.com/library/llama3.3
   3. https://ollama.com/library/qwen3

## Immediate Next Actions

1. ~~Implement Stage 0 bugfixes/tests.~~ (Done)
2. ~~Implement `status_message` field, worker updates, and CLI progress output (Stage 1).~~ (Done)
3. ~~Implement usage/cost metadata persistence and expose it in extraction detail endpoints.~~ (Done as part of Stage 0)
4. ~~Add agent status callback to `extract_findings()` for inner-agent progress (Stage 1.5).~~ (Done)
5. Define strict vs lenient partial-success contract and API/status fields.
6. ~~Establish initial eval datasets (including corrections-derived cases) and baseline scoring report.~~ (Done — Phase 1)
7. Implement Stage 4A file-based example catalog and selector.
8. Design Stage 3.5 baseline coding lookup tables and unresolved-item reporting.
9. Define Stage 4B trigger metrics before building DuckDB retrieval.

## Later Improvements (Deferred from Stage 2 Phase 1.5)

These items were identified during code review of the Phase 1.5 eval harness work:

1. **Assertion-score namespace collision risk in `_extract_averages()`**: If an evaluator returns a bool assertion and a float score with the same metric name, `_extract_averages()` will silently overwrite the score with the assertion pass rate. Currently no collision exists, but this is fragile. Consider namespace-prefixing assertions (e.g., `assertion:verbatim_pass`) or using separate dicts for threshold checking.

2. **`results.json` format change**: `verbatim_pass` moved from `case.scores` to `case.assertions` in per-case results. Any downstream tooling parsing `results.json` needs to check both dicts. Document this as a breaking change in result format if building comparison tools.

3. **`NonFindingClassificationEvaluator` matching consolidation**: The evaluator's inline matching loop (iterate expected non-finding texts, find best Jaccard match in actual, apply threshold) duplicates the same greedy best-match pattern as `match_findings()`. Consider extracting a generic `match_items(expected, actual, token_fn, threshold)` that both finding matching and non-finding matching use.

4. **pydantic-evals upstream feature request**: `report.averages().assertions` returns a single float (overall pass rate), not a per-assertion dict. We work around this by iterating per-case data in `_extract_averages()`. If pydantic-evals adds per-assertion averaging, we can simplify the runner.

5. **Evaluator diagnostic reasons**: Only `FindingDetectionEvaluator` (f1) and `VerbatimQuoteEvaluator` (verbatim_pass) return `EvaluationReason`. Consider adding reasons to other evaluators where counts aid debugging — e.g., `PresenceClassificationEvaluator` could report "5/6 correct" and `LocationEvaluator` could report "3/4 body region, 2/2 laterality".

## Later Improvements (Deferred from Stage 1)

These items were originally scoped for Stage 1 but deferred until the need is clearer:

1. `job_events` table with event type/timestamp/payload for full audit trail.
2. SSE/WebSocket stream endpoint (`GET /api/jobs/{job_id}/events`) for real-time UI updates.
3. CLI live mode consuming event stream.
4. `completed_with_warnings` terminal status (deferred to Stage 3 when partial-success validation exists).
5. Replay/comparison workflow for same-report multi-run diffs.
6. PydanticAI streaming for richer progress (builds on Stage 1.5 callback foundation):
   1. `event_stream_handler` — pass to `agent.run()` for retry/tool-call detection without modifying the validator.
   2. `agent.run_stream_events()` — async-for over all events including token deltas for real-time UI streaming.
   3. `agent.iter()` — node-level iteration for coarse-grained execution control.
   4. Would enable token-level streaming to SSE endpoints, detailed per-call timing, and richer progress messages.
