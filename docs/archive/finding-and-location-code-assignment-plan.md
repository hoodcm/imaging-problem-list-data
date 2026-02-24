# Finding and Location Code Assignment Plan (V3: Batch Per-Chunk Pipeline)

Last updated: 2026-02-19
Status: Completed

## Goal

Replace per-finding deterministic-then-adjudication coding with a batch per-chunk pipeline: deterministic fast-path for exact/synonym hits, then 3 fast LLM calls per chunk to (1) generate diverse search terms, (2) select finding codes from richer candidate sets, (3) select location codes.

## Architecture

```
Per chunk (after extraction):

  ┌─ Deterministic fast-path ──────────────────────┐
  │  index.get(name) → exact/synonym? → coded      │
  └─────────────────────────────────────────────────┘
                    │ unresolved findings
                    ▼
  ┌─ LLM #1: Search Term Generator ────────────────┐
  │  Input: exam info, chunk text, all unresolved   │
  │         findings (name, presence, location)     │
  │  Output: 2-3 search terms per finding + per     │
  │          location                               │
  └─────────────────────────────────────────────────┘
                    │ search terms
                    ▼
  ┌─ Index Searches (parallel) ────────────────────┐
  │  finding index: search(term, limit=8) per term  │
  │  location index: search(term, limit=8) per term │
  │  Dedupe and rank candidates per finding         │
  └─────────────────────────────────────────────────┘
                    │ candidate sets
             ┌──────┴──────┐
             ▼             ▼
  ┌─ LLM #2: Finding  ┌─ LLM #3: Location
  │  Code Selector     │  Code Selector
  │  All findings +    │  All findings +
  │  their candidates  │  their candidates
  │  → select best     │  → select best
  └────────────────    └────────────────
```

## Key Design Decisions

1. **Deterministic fast-path preserved:** `index.get(name)` for exact/synonym hits; skip LLM entirely.
2. **Batch over per-finding:** All 3 LLM calls process all unresolved findings at once with full chunk context.
3. **Larger candidate sets:** `limit=8` per search term, 2-3 terms per finding, deduped.
4. **Non-fatal throughout:** Each LLM call failure falls back gracefully (search term failure → use finding name as term; selector failure → findings stay unresolved).
5. **Replaces legacy pipeline:** Old per-finding adjudication path (`code_assigner.py`, `coding_agents.py`) is retired. `batch_coding.py` + `batch_coding_agents.py` are the new implementation.
6. **No per-finding caching:** Batch context makes per-finding caching less meaningful.

## Implementation

### Files

| File | Role |
|---|---|
| `batch_coding_agents.py` | 3 PydanticAI agents with structured output: search term generator, finding code selector, location code selector |
| `batch_coding.py` | Pipeline orchestrator: fast-path → search terms → index search → code selection → assembly. Also holds shared index infrastructure (moved from `code_assigner.py`) |

### Coding Methods

- `exact` / `synonym`: deterministic fast-path hit
- `batch`: LLM-selected via batch pipeline
- `unresolved`: no match found or LLM failure

### Configuration

- `IPL_CODING_SEARCH_LIMIT` (default 8, range 1-20): max candidates per search term
- `IPL_CODING_MODEL`: model for batch coding agents (falls back to extraction model)
- `IPL_CODING_REASONING`: reasoning mode for coding agents
- `IPL_CODING_MAX_CONCURRENCY`: max concurrent per-chunk coding pipelines
- `IPL_CODING_ENABLED`: master toggle for coding pipeline

### Interface Contract

`batch_apply_coding(extraction, *, chunk_text, model_name, reasoning, search_limit)` returns `ReportExtraction` with inline `findings[].coding`.

The orchestrator calls `apply_coding_fn(extraction, chunk_text=chunk_text)` per chunk.

## Test Coverage

1. `tests/test_batch_coding_agents.py`: response model validation, prompt building
2. `tests/test_batch_coding.py`: full pipeline with mocked agents/indexes, fast-path, fallbacks, error handling

## Deferred Improvements

Near-term (tracked in `docs/pending-refactoring.md`):

- **Rename adjudicator reasoning helper**: `_resolve_coding_adjudicator_reasoning` in `extraction_runtime.py` still references the retired adjudicator concept — rename to `_resolve_coding_reasoning`.
- **Agent factory functions**: Add `_create_*_agent()` factories in `batch_coding_agents.py` so agent configuration is separate from invocation.
- **Agent instance caching**: Currently creates a new agent per call. Cache agents by (model, reasoning) if profiling shows measurable benefit (see `PR-010`).
- **`ApplyCodingFn` → Protocol**: Replace `Callable[..., Awaitable[ReportExtraction]]` with a typed `Protocol` (see `PR-001`).

Longer-horizon (tracked in `docs/future-improvements.md`):

- **Per-phase observability**: Add Logfire/OTel spans to each batch coding phase (fast-path, search terms, index search, finding selection, location selection) for timing and success-rate breakdown.
- **Search term evaluation**: Log LLM-generated search terms alongside finding names; measure whether LLM terms produce better candidates than name-only fallback.
- **Candidate set analysis**: Log candidate set sizes and selection patterns to tune `search_limit` and identify index coverage gaps.

Cleanup (opportunistic):

- Normalize logging style in coding path modules when touched.
- Evaluate wrapping reusable index lifecycle in an explicit async context-manager helper.
