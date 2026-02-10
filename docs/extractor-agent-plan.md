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

## Stage 0: Correctness and Contracts

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

Deliverables:
1. Agent settings refactor (run-time settings as single source of truth).
2. Clear 422/API errors for invalid reasoning values.
3. Model-specific reasoning compatibility matrix in code + tests.
4. Tests for default/override/no-thinking behavior per provider.
5. Persisted usage fields and test coverage for supported/unsupported providers.

Exit criteria:
1. `--reasoning none` and API equivalent verified for OpenAI, Anthropic, Google, Ollama.
2. CI includes new tests and passes.
3. Usage/cost-related metadata is available for model comparison dashboards.

## Stage 1: Status Messages and Run Telemetry

Objective: make extraction progress visible to CLI and web UI.

Scope:
1. Add job event model (`job_events` table) with event type, timestamp, payload.
2. Emit lifecycle events from worker: queued, started, prompt_built, model_call_started, model_call_finished, validator_retry, completed, completed_with_warnings, failed.
3. Add explicit job terminal statuses: `completed`, `completed_with_warnings`, `failed`.
4. Add stream endpoint for UI:
   1. `GET /api/jobs/{job_id}/events` (SSE preferred first, WebSocket optional later).
5. Add CLI live mode consuming same event stream.
6. Capture and store usage/timing metadata per run (latency, retries, token usage when available).
7. Add replay/comparison workflow for iterative model tuning:
   1. re-run extraction for same report with different model/reasoning settings
   2. produce structured diff of findings/attributes/non-finding text between extraction versions
   3. expose via API and simple CLI output for rapid iteration

Implementation note:
1. PydanticAI supports event streaming (`run_stream` / `run_stream_events`); adapt this to internal job event emission.

Exit criteria:
1. Console can show in-flight progress for a running job.
2. Web client can display live status and retries.
3. Post-run audit trail available via API.
4. Report-level extraction comparison/diff is available and test-covered.

## Stage 2: Evaluation Harness and Quality Gates

Objective: make changes measurable and regression-safe.

Scope:
1. Build a versioned eval set from existing sample reports plus new edge-case reports.
2. Add scoring for:
   1. finding presence classification accuracy
   2. location accuracy (body_region/laterality)
   3. attribute extraction precision/recall
   4. verbatim quote exactness
   5. non-finding classification accuracy
3. Split datasets by purpose:
   1. smoke
   2. comprehensive
   3. regression
4. Add automated eval run command and CI threshold checks.
5. Mine correction history into eval/regression datasets:
   1. accepted/applied corrections become high-value regression seeds
   2. rejected corrections inform false-positive filters and evaluator rules

Implementation note:
1. Use Pydantic Evals dataset approach for repeatable case management and serialization.

Exit criteria:
1. Any prompt/example/model-policy change has before/after scores.
2. Regression thresholds are enforced in CI.
3. Corrections-derived cases are included in at least one maintained regression dataset.

## Stage 3: Prompt Refactor and Output Reliability

Objective: improve extraction consistency while reducing token load.

Scope:
1. Split instructions into:
   1. stable policy block
   2. concise task block
   3. dynamically selected examples
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
1. Add Ollama model discovery (`/api/tags`) into `/api/models`.
2. Add model capability registry:
   1. tool-calling support
   2. structured output mode support
   3. thinking support/options
   4. context window
3. Add model profile presets:
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
4. Use SSE first for status streaming; add WebSocket only if bidirectional control becomes necessary.
5. Use public `findingmodel` and `anatomic-locations` packages first; only adopt internal `oidm-common` with explicit pinning strategy.

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

1. Implement Stage 0 bugfixes/tests.
2. Create `job_events` schema and `/api/jobs/{job_id}/events` endpoint scaffold.
3. Define strict vs lenient partial-success contract and API/status fields.
4. Implement usage/cost metadata persistence and expose it in extraction detail endpoints.
5. Add replay/comparison endpoint or CLI workflow for same-report multi-run diffs.
6. Establish initial eval datasets (including corrections-derived cases) and baseline scoring report.
7. Implement Stage 4A file-based example catalog and selector.
8. Design Stage 3.5 baseline coding lookup tables and unresolved-item reporting.
9. Define Stage 4B trigger metrics before building DuckDB retrieval.
