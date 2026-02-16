# Naming Refactoring Plan

## Status (2026-02-16)

Completed in runtime-unification pass:

- `agent.py` -> `extraction_agent.py`
- `extraction_pipeline.py` -> `extraction_runtime.py`

Remaining suggestions below are still optional follow-on work.

## Problem

Several prominent module and class names in `src/finding_extractor/` are too
generic, ambiguous, or collide with other concepts in the codebase.  The worst
offender is the overloaded term "model", which refers to both Pydantic data
models (`models.py`) and AI/LLM models (`model_policy.py`, `model_catalog.py`,
`model_resilience.py`).

## Suggested Renames

| Current | Suggested | Why |
|---|---|---|
| `agent.py` | `extraction_agent.py` | Matches `extraction_orchestrator.py` pattern; says what it's an agent *for* |
| `models.py` | `domain.py` or `schemas.py` | Disambiguates from `model_*.py` (AI models) |
| `store.py` | `persistence.py` or `db.py` | More specific than "store" |
| `tasks.py` | `extraction_jobs.py` | Says what kind of jobs; completes the `extraction_*` module family |
| `broker.py` | `extraction_broker.py` | Says what the broker is for; pairs with `extraction_jobs.py` |
| `providers.py` | `model_providers.py` | Joins the `model_*` family where it belongs |
| `base.py` | `base_model.py` | Minor; clarifies it's a base model class |
| `UnresolvedFinding` | `UnmappedFinding` | It's unmapped to OIFM codes, not "unresolved" in general |
| `Settings` | `ExtractorSettings` | Generic class name; more greppable and avoids collision in import namespace |
| `ExtractorDeps` | *(move to `extraction_agent.py`)* | Agent infrastructure, not a domain concept; doesn't belong in domain models |

## Details

### `agent.py` -> `extraction_agent.py`

The module creates a PydanticAI `Agent`, configures it with the extraction
prompt and verbatim validator, and exposes `extract_findings()` as the main
entry point.  It's specifically the finding extraction engine -- the thing that
takes a report and produces structured findings.  `extraction_agent.py` is the
most straightforward rename and parallels the existing
`extraction_orchestrator.py` and `extraction_pipeline.py` naming pattern.

### `models.py` -> `domain.py` or `schemas.py`

This is the highest-impact rename.  "Model" means two completely different
things in this codebase:

- `models.py` = Pydantic data models (`ReportExtraction`, `ExtractedFinding`, etc.)
- `model_policy.py`, `model_catalog.py`, `model_resilience.py` = AI/LLM model management

When you read `from finding_extractor.models import ...` next to
`from finding_extractor.model_policy import ...`, the semantic collision is
real.

### `store.py` -> `persistence.py` or `db.py`

"Store" could be anything.  It's specifically an async SQLite persistence layer
for reports, extractions, jobs, and corrections.  The class inside,
`ExtractionStore`, is better-named than the module itself.

### `tasks.py` -> `extraction_jobs.py`

"Tasks" is ambiguous -- is it Taskfile tasks? TaskIQ tasks? Todo items?  The
module defines TaskIQ background jobs that run extraction.  `extraction_jobs.py`
says what *kind* of jobs these are and completes the `extraction_*` module
family: `extraction_agent`, `extraction_orchestrator`, `extraction_pipeline`,
`extraction_jobs`, `extraction_broker`.

### `broker.py` -> `extraction_broker.py`

Bare "broker" is generic.  It's specifically the TaskIQ Redis broker
configuration and worker event handlers for extraction jobs.
`extraction_broker.py` pairs naturally with `extraction_jobs.py` and belongs
to the same naming family.

### `providers.py` -> `model_providers.py`

We listed this as "good as-is" initially, but it's actually the odd one out.
It configures provider-specific AI model settings (reasoning modes, thinking
budgets, extraction presets).  It belongs in the `model_*` family alongside
`model_policy.py`, `model_catalog.py`, and `model_resilience.py`.

### `base.py` -> `base_model.py`

Contains a single class, `StrictBaseModel`.  Low priority but would be clearer
if the module ever grows.

### `UnresolvedFinding` -> `UnmappedFinding`

This isn't an "unresolved finding" in the clinical sense.  It's a finding that
couldn't be mapped to an OIFM code.  `UnmappedFinding` (or `UncodedFinding`)
communicates that immediately.

### `Settings` -> `ExtractorSettings`

Every Python project has a `Settings` class.  `ExtractorSettings` is more
greppable and less likely to collide with other settings classes in the import
namespace.

### `ExtractorDeps` -- move out of `models.py`

`ExtractorDeps` is a PydanticAI agent dependency container (holds `report_text`
and `status_callback`).  It's agent infrastructure, not a domain concept.  When
`models.py` is renamed to `domain.py`, `ExtractorDeps` should move into
`extraction_agent.py` rather than staying in the domain module.

## Stale References

`examples.py` is documented in CLAUDE.md as "Few-shot extraction examples
loaded dynamically" but does not exist on disk.  Either it was removed or
renamed -- the CLAUDE.md reference should be updated or the file located.

## Names That Are Good As-Is

- **`prompt.py`** with its `_BLOCK` suffix convention -- clear and composable
- **`model_policy.py`**, **`model_catalog.py`**, **`model_resilience.py`** --
  excellent trio; each name tells you exactly what aspect of AI model management
  it handles
- **`extraction_orchestrator.py`**, **`extraction_pipeline.py`** -- clear and
  appropriately distinguished
- **`verbatim.py`**, **`report_sections.py`** -- descriptive, domain-specific
- **`coding_bridge.py`** -- correct domain language ("coding" = assigning
  classification codes in medical terminology, not software development).  May
  confuse newcomers; the module docstring should clarify that "coding" refers to
  OIFM terminology mapping, not programming
- **`config.py`** -- standard and unambiguous
- The **`api_*.py`** family -- consistent prefix convention; each suffix
  (`routes`, `models`, `services`, `dependencies`) maps to a well-known FastAPI
  layer
