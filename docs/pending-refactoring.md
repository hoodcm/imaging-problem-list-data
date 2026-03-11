# Pending Refactoring Backlog

Last updated: 2026-03-11
Status: Active

This is the canonical near-term refactoring/cleanup queue.

## Active Queue

| ID | Priority | Item | Origin |
|---|---|---|---|
| ~~PR-001~~ | ~~high~~ | ~~Replace broad callable aliases (`Callable[..., ...]`) with explicit `Protocol` signatures for orchestrator/runtime call sites.~~ Resolved (created `extractor/progress.py` with `ProgressCallback` Protocol and `ProgressCallbackType` alias). | imported from former `docs/code-review-2026-02-15.md`; also tracked in stream A |
| ~~PR-002~~ | ~~high~~ | ~~Normalize status callback type aliasing and converge duplicate emit helpers (`_emit_stage` / `_emit`) where practical.~~ Resolved (consolidated into `extractor/progress.py`: `emit_stage_progress()` + `format_stage_status()`). | `docs/extractor-agent-roadmap.md` |
| ~~PR-003~~ | ~~high~~ | ~~Move OpenAI gpt-5 reasoning workaround (`none -> minimal`) out of runtime layer and into provider settings/policy layer.~~ Resolved (agent-refactor: reasoning cleanup consolidated into `resolve_runtime_reasoning()` and provider-specific normalization in `get_model_settings()`). | `docs/extractor-agent-roadmap.md` |
| PR-004 | medium | De-duplicate review-callback wiring between `worker/extraction_jobs.py` and `extractor/runtime.py`. | `docs/extractor-agent-roadmap.md` |
| PR-005 | medium | Expand targeted tests for `extraction_review` label allowlist/reextract decisions, and model-catalog fallback regression. | `docs/extractor-agent-roadmap.md` |
| ~~PR-006~~ | ~~medium~~ | ~~Simplify or remove `ValidationResult.is_valid` if redundant with error lists.~~ Resolved (removed field; callers check `len(verbatim_errors) == 0`). | imported from former `docs/code-review-2026-02-15.md` |
| PR-007 | medium | Add/confirm inline orchestrator comments documenting findings/impression extraction gate semantics. | `docs/extractor-agent-roadmap.md` |
| PR-008 | medium | Unify logging style in touched runtime modules (`structlog` vs stdlib logging). | `docs/extractor-agent-roadmap.md`, `docs/logging-internals.md` |
| PR-009 | medium | Audit extractor UI status handling and ensure canonical stage/status-event contract only (no legacy-status assumptions). | `docs/archive/ui-impact-runtime-unification.md` |
| PR-010 | low | Evaluate lightweight agent-instance caching per model only if profiling shows measurable benefit. | imported from former `docs/code-review-2026-02-15.md` |
| PR-011 | low | Consolidate minor helper duplication: passthrough chunk helper reuse and review-callback wiring reuse. | `docs/extractor-agent-roadmap.md` |
| ~~PR-012~~ | ~~low~~ | ~~Resolve stale CLAUDE reference to non-existent `examples.py`.~~ Resolved (package restructuring: `examples/` is now a subpackage with `__init__.py`). | imported from former `docs/naming_refactoring.md` |
| ~~PR-013~~ | ~~**active**~~ | ~~Decide whether broad module renames are worth execution cost now: `models.py`, `store.py`, `tasks.py`, `broker.py`, `base.py`, and `Settings` type rename.~~ Resolved (package restructuring: modules moved into `db/`, `worker/`, `core/`, `cli/`, `api/`, `llm/` subpackages). | imported from former `docs/naming_refactoring.md` |
| ~~PR-014~~ | ~~**active**~~ | ~~Decide whether `ExtractorDeps` should move from domain-model module to extraction-agent module.~~ Resolved (package restructuring). | imported from former `docs/naming_refactoring.md` |
| PR-015 | low | Reconcile archived CLI persistence residuals: keep/retire `--store-include-validation` and confirm explicit `--store` failure/validation exit-code tests. | `docs/archive/persistence-cli-plan.md` |
| PR-016 | low | Keep fixture-catalog docs synchronized with shared fixture changes (`tests/conftest.py` vs `docs/testing-practices.md`). | `docs/archive/testing_plan.md` |
| ~~PR-017~~ | ~~**active**~~ | ~~Move `coding_summary.py` toward CLI/API presentation layer — it's a read-side display concern, not an extraction pipeline concern.~~ Resolved (package restructuring). | coding decoupling review |
| ~~PR-018~~ | ~~low~~ | ~~Remove dead `_resolve_coding_adjudicator_reasoning()` from `extraction_runtime.py` — orphaned by coding decoupling merge.~~ Resolved. | validator merge review |

## Imported Item Ledger (From Deleted Source Docs)

### Former `docs/code-review-2026-02-15.md`

| Legacy Item | Current Status | Tracking |
|---|---|---|
| Add `UsageLimits` on agent runs | resolved | implemented |
| Unify verbatim-match logic | resolved | implemented |
| Add global test guard to block live model calls by default | resolved | implemented |
| Switch to typed exception mapping (`isinstance`) in public error mapper | resolved | implemented |
| Fallback-model resilience | resolved | implemented |
| Provider-level request concurrency limiting | resolved | implemented |
| Replace `getattr` settings indirection with typed access | resolved | implemented |
| Fix/remove `ValidationResult.is_valid` dead field | resolved | `PR-006` |
| Log suppressed failure-path persistence errors | resolved | implemented |
| Streaming progress to client (SSE/WS) | future | `docs/future-improvements.md` (`FI-001`) |
| Evaluate PydanticAI Graph API | future | `docs/future-improvements.md` (`FI-002`) |
| Add stage-level Logfire/OTel spans | future | `docs/future-improvements.md` (`FI-003`) |
| Cache agent instances by model | open-low | `PR-010` |

### Former `docs/naming_refactoring.md`

| Legacy Item | Current Status | Tracking |
|---|---|---|
| `agent.py -> extraction_agent.py` | resolved | implemented |
| `extraction_pipeline.py -> extraction_runtime.py` | resolved | implemented |
| `models.py -> domain.py/schemas.py` | resolved | `PR-013` (package restructuring) |
| `store.py -> persistence.py/db.py` | resolved | `PR-013` (moved to `db/store.py`) |
| `tasks.py -> extraction_jobs.py` | resolved | `PR-013` (moved to `worker/extraction_jobs.py`) |
| `broker.py -> extraction_broker.py` | resolved | `PR-013` (moved to `worker/broker.py`) |
| `providers.py -> model_providers.py` | resolved | moved to `llm_config/providers.py` in agent-refactor |
| `base.py -> base_model.py` | resolved | `PR-013` (moved to `core/base_model.py`) |
| `Settings -> ExtractorSettings` | resolved | `PR-013` (package restructuring) |
| `ExtractorDeps` move to `extraction_agent.py` | resolved | `PR-014` (package restructuring) |
| stale `examples.py` reference in CLAUDE docs | resolved | `PR-012` (now `examples/__init__.py`) |
| `UnresolvedFinding -> UnmappedFinding` | superseded | coding contract evolved; no standalone rename task needed now |

## Scope Rules

- Add near-term cleanup/refactor items here.
- Keep longer-horizon improvements in `docs/future-improvements.md`.
- When an item is completed, update this file and add a concise entry to `docs/DEV_LOG.md`.
