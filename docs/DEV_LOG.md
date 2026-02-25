# Development Log

Older entries through 2026-02-17 are archived in [archive/dev-log-through-2026-02-17.md](archive/dev-log-through-2026-02-17.md).

---

## 2026-02-25 — Agent refactor: naming, reasoning cleanup, subpackages

Rationalized naming, consolidated reasoning resolution, and restructured the
package into `llm_config/` and `extractor/` subpackages.

1. **Naming rationalization:** Aligned extraction-side naming with validator
   chunk-scoped conventions. `SectionExtractionUnit` → `ReportChunk`,
   `SectionExtractionOutcome` → `ChunkExtractionOutcome`. All field, parameter,
   local variable, and status-event references updated from "unit" to "chunk"
   vocabulary throughout orchestrator, runtime, tasks, and tests.

2. **Reasoning resolution cleanup:** Removed redundant `resolve_effective_reasoning()`.
   Purified `get_model_settings()` to be a pure builder (returns `None` when
   reasoning is `None`). Consolidated all runtime reasoning resolution onto
   `resolve_runtime_reasoning()`.

3. **`llm_config/` subpackage:** Moved `model_defaults.py`, `model_policy.py`,
   `model_catalog.py`, `model_resilience.py`, `providers.py` into
   `src/finding_extractor/llm_config/`. Clean-break migration — no re-export shims.

4. **`extractor/` subpackage:** Moved `extraction_orchestrator.py`,
   `extraction_agent.py`, `extraction_runtime.py`, `extraction_review.py`,
   `exam_info_agent.py` into `src/finding_extractor/extractor/`. Clean-break
   migration — no re-export shims.

5. **Documentation:** Updated CLAUDE.md structure, extraction-internals.md module
   paths and vocabulary, coding-agent-design.md references, pending-refactoring.md
   (PR-003 resolved, PR-013 providers.py resolved), semantic-chunking-plan.md,
   agent-restructuring.md, and report-sections.md/extraction-usage.md import paths.

Verification: lint clean, 561 tests passing.

## 2026-02-23 — Decouple coding from extraction pipeline

Stripped all inline OIFM coding from the extraction path. Coding is now an
independent tool, triggered separately from extraction.

1. **Design doc:** Created `docs/coding-agent-design.md` capturing architecture
   (3-call LLM pipeline), index search strategy, prompt design principles,
   response models, independent job design, and lessons learned from prototyping.
2. **Extraction stripping:** Removed `ApplyCodingFn` wiring, `coding_enabled` and
   all `coding_*` config fields, worker shutdown hook, dead `on_outcome` parameter
   from orchestrator.
3. **Deleted files:** `batch_coding.py`, `batch_coding_agents.py`, `code_assigner.py`,
   `coding_agents.py` (and their tests).
4. **Archived:** `finding-and-location-code-assignment-plan.md` moved to `docs/archive/`.
5. **Backlog updates:** Added PR-017 (move `coding_summary.py` to presentation layer),
   FI-012 (independent coding agent testability). Removed completed/superseded items.
6. **Branch:** Created `coding-agent` worktree for standalone coding agent implementation.

Verification: `task lint` clean, 536 tests passing.

## 2026-02-19 — Batch coding pipeline refactoring (code review fixes)

Post-review structural improvements to batch coding pipeline:

1. **God function decomposition** (`batch_coding.py`): Broke 360-line `batch_apply_coding`
   into focused phase functions: `_run_fast_path`, `_assemble_fast_path_only`,
   `_build_unresolved_descriptors`, `_generate_terms`, `_search_all_candidates`,
   `_select_findings`, `_select_locations`, `_assemble_results`. Main function is now
   a thin orchestrator calling phases in sequence.

2. **Selection pattern deduplication** (`batch_coding.py`): Extracted shared helpers
   `_is_valid_selection`, `_finding_alternates`, `_location_alternates`,
   `_unresolved_finding_code`, `_unresolved_location_code` — removes near-identical
   code between Phase 3 (finding selection) and Phase 4 (location selection).

3. **Prompt builder consolidation** (`batch_coding_agents.py`): Three nearly-identical
   prompt builders (`_build_search_term_prompt`, `_build_finding_selector_prompt`,
   `_build_location_selector_prompt`) replaced with shared `_build_prompt(instruction, *,
   exam_info, chunk_text, findings)` plus per-agent instruction constants.

4. **Typed inter-module interfaces** (`batch_coding_agents.py`): Replaced `dict[str, Any]`
   parameters with `TypedDict` interfaces: `FindingDescriptor`, `FindingWithCandidates`,
   `LocationWithCandidates`. Used at construction sites in `batch_coding.py` and agent
   function signatures.

5. **Documentation**: Added deferred items (PR-017, PR-018) and future ideas (FI-012
   through FI-014) to backlog docs.

## 2026-02-19 — Batch coding pipeline (replaces per-finding adjudication)

Replaced per-finding deterministic+adjudication coding pipeline with batch per-chunk
3-call LLM pipeline:

1. **New files:**
   - `batch_coding_agents.py`: 3 PydanticAI agents (search term generator, finding
     code selector, location code selector) with structured output models.
   - `batch_coding.py`: pipeline orchestrator — deterministic fast-path, then 3 LLM
     calls per chunk for unresolved findings. Includes index infrastructure moved
     from `code_assigner.py`.

2. **Wiring changes:**
   - `models.py`: added `"batch"` to `CodingMethod` and `LocationCodingMethod`.
   - `extraction_orchestrator.py`: `ApplyCodingFn` now variadic; passes `chunk_text`
     to coding function.
   - `extraction_runtime.py`: default coding function calls `batch_apply_coding`.
   - `config.py`: replaced `coding_adjudication_enabled` with `coding_search_limit`.
   - `broker.py`: updated import for `close_reusable_coding_indexes`.

3. **Retired files:** `code_assigner.py`, `coding_agents.py` (and their tests).

4. **New tests:** `test_batch_coding_agents.py` (10 tests), `test_batch_coding.py`
   (11 tests). Updated orchestrator and runtime tests for new signatures.

## 2026-02-19 — Runtime contract alignment (exam-info context + always-on validator)

1. Expanded exam-info sub-agent payload wiring:
   - orchestrator now passes `source_ref`, external metadata, and deterministic
     header-focused report context to `extract_exam_info`.
   - exam-info prompt builder now includes those fields and only falls back to
     report preview when header context is unavailable.
2. Validator review is now always-on in runtime:
   - removed `validator_review_enabled` setting and `IPL_VALIDATOR_REVIEW_ENABLED`.
   - `validator_reextract_enabled` remains the retry control for validator requests.
3. Added regression/contract tests:
   - cache-key regression ensuring adjudication caching keys on `evidence_text`.
   - exam-info context forwarding tests at runtime and orchestrator layers.
4. Documentation alignment updates:
   - `docs/configuration.md` + `config.toml.example` updated for always-on validator.
   - `docs/extraction-internals.md`, `docs/extraction-usage.md`,
     `docs/eval-internals.md`, and orchestrator plan stage vocabulary aligned with
     current runtime behavior.

## 2026-02-18 - Documentation cleanup and restructuring

1. Added `docs/README.md` as categorized index of all documentation.
2. Archived 23 completed/historical docs to `docs/archive/`:
   - 12 completed stage/stream docs from `extractor-agent-plans/`
   - 2 one-time artifacts (`ui-improvement-fixes.md`, `ui-impact-runtime-unification.md`)
   - 9 completed plan docs (`testing_plan.md`, `batch-runner-plan.md`, `data-model-plan.md`, `config-plan.md`, `migration-architecture.md`, `api-server.md`, `extractor-frontend.md`, `database-layer.md`, `logging-plan.md`)
3. Updated all cross-references in active docs to point to `archive/` paths.
4. Updated root `README.md` to remove stale doc references.
5. Rotated DEV_LOG.md (121K → fresh start; full history in archive).

## 2026-02-18 — Orchestrator next-phase: exam-info, coding context, validator feedback, timeouts

Implemented all four "Immediate Next Work Items" from the orchestrator core plan:

1. **Exam-info sub-agent** (`exam_info_agent.py`): dedicated agent extracts modality,
   body part, and laterality from the report header. Runs in parallel with chunk
   extraction via `asyncio.create_task`; non-fatal on failure (keeps placeholder).
   Added `laterality` field to `ExamInfo` model.
2. **Coding adjudicator context upgrade** (`coding_agents.py`, `code_assigner.py`):
   adjudication prompts now receive exam info, presence, location fields, and evidence
   text. Cache key includes exam context to prevent cross-report stale hits.
   Renamed `code_assinger.py` → `code_assigner.py` (typo fix).
3. **Validator review with feedback** (`extraction_review.py`, `extraction_orchestrator.py`):
   `ReviewRequest` model carries per-unit feedback and suspected_issue. Feedback is
   threaded to retry units and appended to chunk extraction prompts. Validator review
   now runs unconditionally in the V2 runtime.
4. **Per-piece timeouts** (`config.py`, `extraction_orchestrator.py`):
   `subagent_timeout_seconds` (default 20s) wraps chunk extraction, coding, validator
   review, and exam-info await. All timeout paths are non-fatal except chunk extraction
   (which feeds into existing repair logic).

Bug fixes from code review:
- Coding cache key now includes exam context fields and evidence text to prevent stale adjudication reuse.
- Exam-info task is cancelled on early orchestrator failure (all chunks fail).

Test coverage: 15 new/updated orchestrator tests covering parallel exec, timeouts,
feedback threading, non-fatal failures. 60 tests passing across affected modules.

## 2026-02-18 - Chunk sub-agent wiring + model guidance docs

1. Wired orchestrator chunk-unit extraction calls to the dedicated chunk prompt/schema path:
   - runtime/worker now use `extract_chunk_findings` for unit extraction
   - chunk context fields (`section_name`, prev/next context) are passed explicitly
2. Kept final assembled contract unchanged (`ReportExtraction`) while adapting chunk payloads.
3. Updated extraction docs to reflect chunk sub-agent behavior:
   - `docs/extraction-internals.md`
   - `docs/extraction-usage.md`
4. Added model guidance reference:
   - `docs/model-selection-notes.md`
5. Updated active plan docs for remaining orchestrator work and future ideas:
   - `docs/extractor-agent-plans/orchestrator-core-plan.md`
   - `docs/extractor-agent-plans/chunk-extraction-prompt-schema-plan.md`
   - `docs/future-improvements.md` (dynamic example selection backlog item)

## 2026-02-24 - Validator hard cutover to single-chunk review contract

1. Replaced report-level validator request flow with single-chunk review decisions:
   - one validator call per `report_chunk_id`
   - one `ExtractionReviewDecision` per chunk
   - problem list typed as `ExtractionReviewProblem` with `extract_problem_type`
2. Updated orchestrator validator stage behavior:
   - chunk-scoped review status events (`chunk_review_start`, `chunk_review_decision`)
   - targeted re-extraction with structured feedback threaded into chunk prompt
   - final review summary detail event
3. Updated validator prompt contract and payload shape to chunk-level naming:
   - canonical fields: `REPORT_CHUNK_ID`, `EXAM_INFO`, `PRECEDING_CHUNK_CONTEXT`,
     `REPORT_CHUNK`, `FOLLOWING_CHUNK_CONTEXT`, `CHUNK_EXTRACTION`
   - required `EXTRACTION_TASK_SUMMARY` block
4. Moved validator prompt artifact to `prompts/validator_prompt_example.md`
   and removed the stale root-level `validator_prompt_example.md`.
5. Updated active plan/docs to align with the new schema and terminology.


## 2026-02-24 - Runtime reasoning policy + canonical model defaults cleanup

1. Added canonical model constants and curated common model list in `src/finding_extractor/model_defaults.py`.
2. Updated defaults/presets/docs to align on current baseline models:
   - default extraction: `google-gla:gemini-3-flash-preview`
   - fallback extraction: `openai:gpt-5.2`
   - quality preset / validator default example: `anthropic:claude-opus-4-6`
   - local options: `ollama:qwen3:30b-instruct`, `ollama:qwen3:30b-thinking`, `ollama:gpt-oss:120b`
3. Unified API/batch/eval/runtime reasoning preflight on `resolve_runtime_reasoning(...)` with model-family-aware normalization and strict unknown-family fail-fast (override via `IPL_ALLOW_UNKNOWN_MODEL_REASONING=true`).
4. Made Ollama reasoning behavior model-specific in provider settings/capabilities:
   - Qwen3 thinking variants accept thinking levels
   - Qwen3 instruct remains `none` only
   - GPT-OSS 120B supports tiered `think` levels (`minimal` normalized to `low`)
5. Switched secrets handling to unprefixed env names where applicable:
   - Logfire token is `LOGFIRE_TOKEN` (env-only; rejected in `config.toml`)
6. Updated CLI/docs semantics so coverage validation is enabled by default (`--validate/--no-validate`, default `--validate`) and clarified usage guidance.
