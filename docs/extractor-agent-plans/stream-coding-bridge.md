# Stream Coding Bridge: Stage 3.5 Baseline OIFM + Location Mapping

Last updated: 2026-02-15
Status: Ready for kickoff (next push Stream 3)

## Kickoff target

- Worktree: `/Users/talkasab/repos/imaging-problem-list-provider`
- Branch: `feature/coding-bridge-followon-slice1`

## Current cycle note

Current implementation work is split into:

1. Runtime hardening: `docs/extractor-agent-plans/stream-coding-runtime-hardening.md`
2. API/UI contract: `docs/extractor-agent-plans/stream-coding-api-ui-contract.md`

This document remains the historical baseline and Stage 7 direction reference.

## Immediate next steps (implement before next feature work)

1. **Index lifecycle management.** `apply_coding()` currently opens fresh `Index()` and `AnatomicLocationIndex()` on every invocation, creating new DuckDB connections each time. In a worker processing many extractions, this is wasteful. The indices should be opened once at worker startup (or lazily on first use) and reused across calls. Consider a module-level or dependency-injected index holder.

2. **Use `region` parameter on `AnatomicLocationIndex.search()`.** The search API supports a `region` kwarg to filter results by anatomic region (e.g., `"Abdomen"`, `"Thorax"`). We already have `body_region` from the finding's `FindingLocation`. Passing it as a filter would improve location match quality for free.

## Stage definition

Stage 3.5 adds an initial deterministic coding layer after extraction to provide partial structured coding without blocking extraction completion.

## What shipped

### Deterministic coding pipeline (`coding_bridge.py`)

A 3-tier finding mapping strategy:

1. **Exact match** — `index.get(finding_name)` resolves by OIFM ID, name, or slug (confidence 1.0).
2. **Synonym match** — same `get()` call matches against synonym lists (confidence 0.9).
3. **Search** — `index.search(finding_name, limit=3)` uses hybrid BM25 + optional semantic search via `findingmodel` package (confidence 0.7).
4. **Unresolved** — no confident match; finding lands in the unresolved list.

Anatomic location mapping uses `anatomic-locations` package to map `FindingLocation` fields to RadLex RID references.

### Data model additions (`models.py`)

- `CodingMethod` literal: `"exact"`, `"synonym"`, `"search"`, `"agent"`, `"unresolved"`
- `FindingCoding` — per-finding OIFM code result with method, confidence, alternates
- `LocationCoding` — per-finding anatomic RID result
- `UnresolvedFinding` — finding that couldn't be coded, with reason and candidates
- `AlternateCode` — candidate code with score
- `CodingBridgeResult` — run-level container with parallel arrays and summary counts

### Integration

- **Feature flag**: `IPL_CODING_ENABLED` (default `false`) in `config.py`
- **Task pipeline**: wired into `_run_extraction_impl()` after validation, before persistence
- **Persistence**: `coding_json` column on `extractions` table (nullable TEXT)
- **Error isolation**: coding failures never fail extraction; per-finding and whole-bridge error handling

### Dependencies

- `findingmodel>=1.0.0` — DuckDB-backed OIFM index with exact/synonym lookup and hybrid search
- `anatomic-locations>=0.2.0` — DuckDB-backed anatomic location index with search

## Design decisions for future agent-based coding (Stage 7)

The deterministic layer is explicitly a **minimal first pass**. The architecture is designed for a smooth transition to an LLM-based coding agent:

1. **`CodingMethod` includes `"agent"`** — reserved in the literal now so the schema doesn't need to change when the agent layer arrives.

2. **The unresolved list is the natural agent handoff** — it captures exactly the findings the deterministic layer couldn't resolve, with candidates when available. A future coding agent consumes this list as its input: "here are the ambiguous cases, use clinical reasoning to resolve them."

3. **`apply_coding()` is the stable interface** — callers (tasks.py) don't know or care whether coding came from dictionary lookup or an agent. The agent-based implementation slots in behind the same function signature, potentially as a second pass after the deterministic layer.

4. **Confidence + alternates already model agent output** — an agent can set its own confidence scores, explain its reasoning via the alternates list, and use the same `FindingCoding` structure.

5. **Storage is method-agnostic** — `coding_json` serializes `CodingBridgeResult` regardless of how each finding was coded. A single result can mix deterministic and agent-coded findings.

6. **Likely agent architecture**: the deterministic layer runs first (fast, free), then the agent handles only unresolved/low-confidence items. This keeps cost down and latency bounded while improving coverage.

## Non-goals (unchanged)

1. Full semantic coding agent (future Stage 7 work).
2. Job failure due solely to coding miss.

## Remaining work

- Expose coding results in API responses (`GET /api/extractions/{id}`)
- Surface coding data in the extractor UI (coded/unresolved badges per finding)
- Tuning: evaluate search confidence threshold; consider raising from 0.7
- Stage 7: agent-based coding for unresolved findings using LLM clinical reasoning
