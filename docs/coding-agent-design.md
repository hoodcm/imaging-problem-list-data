# Coding Agent Design

Blueprint for the standalone OIFM finding code and anatomic location code assignment tool.

Last updated: 2026-02-24

## Overview

Coding assigns OIFM finding codes and anatomic location codes to extracted findings. It is an **independent job** — fully decoupled from extraction. Extraction output persists without codes; coding is triggered separately and can be re-run with different models or settings.

## Naming Alignment with Extraction Pipeline

The coding agent should adopt the chunk-scoped naming conventions established by the validator redesign:

- `report_chunk_id` (not `unit_label`) — identifies the source chunk for provenance
- `preceding_chunk_context` / `following_chunk_context` — context window naming
- `chunk_extraction` — the extraction payload for a chunk
- `raw_extracted_finding_index` — zero-indexed finding position within a chunk

These names are canonical across the extraction, validator, and coding subsystems.

## Architecture

### 3-Call LLM Pipeline (Per Chunk)

Each chunk of extracted findings goes through a three-call pipeline:

1. **Search term generation** — LLM proposes 2-3 diverse query terms per finding (for finding code) and per finding (for location code).
2. **Index search** — embed terms, search the OIFM finding index and anatomic location index for candidate codes.
3. **Code selection** — LLM selects the best code from each candidate set, or marks the finding as unresolved.

Finding code selection and location code selection run as **parallel LLM calls** (`asyncio.gather`).

### Fast-Path Optimization

- **Finding codes:** `FindingIndex.get(name)` performs exact/synonym lookup. If it resolves, skip the LLM pipeline for the finding code.
- **Location codes:** Always go through LLM selection. The deterministic top-1 approach was tested during prototyping and proved inadequate — location assignment requires contextual reasoning.

### Non-Fatal Per-Phase Design

Each phase catches exceptions independently and degrades gracefully:

- Search term generation failure → use `finding_name` as the fallback search term.
- Index search failure → skip coding for that finding (mark unresolved).
- Code selection failure → mark unresolved.
- One finding's failure does not block other findings in the same chunk.

## Index Search Strategy

### Finding Index

- `search_batch(all_unique_terms, limit=8)` — one batch embedding call across all search terms in the chunk.
- Results distributed back to each finding based on which terms belong to which finding.
- Process-level async lock guards the shared singleton index instance.

### Location Index

- Serial per-term `search(term, limit=8, region=...)` — the upstream `AnatomicLocationIndex` does not currently support batch search.
- Process-level async lock guards the shared singleton index instance.
- **Upstream feature request:** `AnatomicLocationIndex.search_batch()` and name-based `get()` would unlock batch optimization parity with the finding index.

## Prompt Design Principles

These will be refined collaboratively during implementation:

- **Role:** Medical informatics assistant proposing query terms for standard ontologies.
- **Directionality:** Slightly more general is acceptable (e.g., "kidney abnormality" for "renal mass"), but never more specific (NOT "oncocytoma" for "renal mass").
- **Standard terminology only** — no acronyms in search terms.
- **Context:** All three prompts receive:
  - Exam info (modality, body part, laterality)
  - `report_chunk` text (truncated to 1500 chars)
  - `preceding_chunk_context` (similarly capped)
  - `following_chunk_context` (similarly capped)

## Response Models

### `SearchTermGeneratorOutput`

Per-finding search terms and per-finding location search terms.

- `search_terms`: list of terms (validated: `min_length=1`, `max_length=5`)
- `location_search_terms`: list of terms (same constraints)

### `FindingCodeSelectorOutput`

Per-finding OIFM code selection (or unresolved).

- Selected `oifm_id` validated against the candidate set — an ID not present in candidates is treated as unresolved.

### `LocationCodeSelectorOutput`

Per-finding anatomic location selection (or unresolved).

- Selected location ID validated against the candidate set — same validation rule.

All models use `StrictBaseModel`.

## Independent Job Design

### Extraction Output Unchanged

- `coding` field on `ExtractedFinding` already defaults to `None`.
- Uncoded extractions persist fine via `extraction_json`.
- No extraction schema changes needed.

### Chunk Provenance

Mapping findings back to their source chunks is a coding-agent concern — solved on the coding-agent branch, not during the extraction stripping step.

### Trigger Model

- Coding is always **explicitly triggered** (never automatic).
- Can be retriggered with different model/settings.
- New API endpoint: `POST /extractions/{id}/code`

### Configuration

New coding-agent-specific settings (will live in the coding agent's own config section):

- `coding_model` — model for coding LLM calls (use `llm_config.defaults` canonical constants)
- `coding_reasoning` — reasoning level for coding calls
- `coding_max_concurrency` — semaphore limit for parallel chunk coding
- `coding_search_limit` — number of candidates per index search

### Model and Reasoning Infrastructure

The coding agent should reuse the infrastructure established in the validator redesign:

- **Model constants:** Import canonical model IDs from `llm_config.defaults` (e.g., `MODEL_OPENAI_GPT_5_2`). Use `COMMON_MODELS` registry for curated model choices.
- **Reasoning resolution:** Use `resolve_runtime_reasoning()` from `llm_config.providers` for all model reasoning resolution. This handles provider-specific normalization (e.g., OpenAI gpt-5.2 rejects `"minimal"` → auto-maps to `"low"`), unknown-model fail-fast, and the `allow_unknown_model_reasoning` override.
- **Model separation:** If coding adds a validator/adjudicator pattern, enforce model separation as extraction does (validator model must differ from extraction model).

## Lessons Learned From Prototyping

### Location Coding Needs LLM

The deterministic fast-path (blind top-1 from index) was tested for location assignment and proved inadequate. Location assignment requires contextual reasoning even when the finding code resolves via fast-path. The LLM selection step is mandatory for locations.

### Context Forwarding Matters

Previous/next half-chunk context improves all three LLM calls:

- Search term generation benefits from surrounding context for disambiguating terse findings.
- Code selection benefits from context for choosing between similar candidates.

### Concurrency Semaphore

`coding_max_concurrency` was accidentally dropped during the prototype-to-batch refactor. It must be carried forward — without it, large reports with many chunks can overwhelm provider rate limits.

## Validator Feedback Pattern (Reference)

The validator redesign established a structured feedback pattern that the coding agent can reference for its own retry/adjudication flows:

- `PREVIOUS_CHUNK_EXTRACTION` section: formatted table of `raw_extracted_finding_index | finding_name | ...`
- `RE-EXTRACTION_FEEDBACK` section: indexed problems with `extract_problem_type` + `problem_detail`
- `ExtractionReviewDecision` per chunk with `should_reextract`, `problems[]`, `rationale`
- `build_feedback_text()` method on `ExtractionReviewDecision` for structured prompt assembly

If the coding agent introduces an adjudication review step, this pattern provides a proven template.

## Implementation Plan

Work proceeds on the `coding-agent` branch (branched from the clean extraction-only commit):

1. Scaffold coding agents and runner fresh, using `llm_config.defaults` and `resolve_runtime_reasoning()`.
2. Collaborative prompt review — show each prompt explicitly, iterate together.
3. Build out `coding_runner.py`, task, and API endpoint.
4. Add tests.
