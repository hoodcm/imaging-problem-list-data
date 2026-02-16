# Findings/Impression Chunking Plan (Throughput-Focused)

Last updated: 2026-02-16

## Topline Strategy
1. Keep deterministic section splitting.
2. Only run extraction work on `findings` and `impression` sections.
3. For both `findings` and `impression`, if sentence count is below threshold, do not chunk.
4. For `impression` when sentence count is at/above threshold:
   - if list structure is present, use list-item chunking (2-3 items per chunk)
   - otherwise, always use semantic chunking
5. For `findings` when sentence count is at/above threshold, use threshold-based semantic routing.
6. Cap final chunks by sentence-group sizing where applicable.
7. Run chunk-level extraction units in parallel with bounded concurrency.

## Why This Direction
1. Throughput: avoid expensive boundary-adjudication calls.
2. Focus: skip known non-finding sections (`technique`, `history`, `comparison`, etc.).
3. Quality: preserve coherent chunk boundaries for longer findings/impression text.
4. Reliability: deterministic fallback remains available when semantic chunking errors.

## Current Design Contract
1. Section selection:
   - accepted: `findings`, `impression`
   - parsed reports without either section: fail fast in modular mode
   - unsectioned reports: fallback single full-report unit
2. Chunking policy per selected section:
   - stage A: deterministic sentence-span split (for counting + base grouping)
   - stage A-: below-threshold passthrough (single whole-section chunk)
   - stage A0 (impression only): list-item chunking for numbered/bulleted impressions, grouped in 2-3 item chunks
   - stage B (impression): `SemanticChunker` always when no list structure is detected
   - stage B (findings): `SemanticChunker` when sentence-count trigger is exceeded
3. Fallback policy:
   - if semantic chunking fails, use sentence chunks for that section
4. No LLM boundary adjudication in this phase.

## Section Splitting Policy (Deterministic)
1. Keep a strict radiology-domain whitelist of canonical headers:
   - `findings`, `impression`, `technique`, `indication`, `clinical_history`, `comparison`, `recommendation`, `addendum`
2. Normalize header candidates before matching:
   - case fold, whitespace collapse, markdown/bold marker stripping, leading list marker stripping
3. Use curated alias borrowing from radiology section corpora (not full medSpaCy catalogs):
   - include high-value variants such as plural/compound/misspelled forms (`impressions`, `impresson`, `comparision`, `finsings`)
4. Keep deterministic guardrails:
   - header syntax still required (`:`, `-`, markdown/bold heading forms)
   - unknown headers remain ignored

## Current Edge-Case Behavior (Documented)
1. Impression-only reports:
   - supported; modular extraction proceeds with a single `impression` unit.
2. Combined header reports:
   - `Findings/Impression` is currently canonicalized to `findings` and extracted as one unit.
3. Unheaded findings body before impression:
   - when no explicit `findings` header exists, infer `findings` from the final contiguous non-empty text block immediately before first `impression`.
4. Radiology aliases in active use:
   - `body` and `comment(s)` map to `findings`
   - `conclusion(s)` and common misspellings (for example `impresson`) map to `impression`
   - `recommendation(s)` variants and `addendum` are recognized section headers
5. Extraction scope remains unchanged:
   - only `findings` and `impression` become extraction units; other detected sections remain non-extracted context.
6. Impression list parsing:
   - if an `impression` section is formatted as numbered/bulleted list items and sentence threshold is met, chunk by list items first and group as 2-3 items per extraction unit.

## Configuration Surface (Current)
1. `IPL_CHUNKING_ENABLED`
2. `IPL_CHUNKING_SEMANTIC_TRIGGER_SENTENCE_COUNT` (default `4`, so below-threshold sections pass through unchunked)
3. `IPL_CHUNKING_IMPRESSION_LIST_CHUNKING_ENABLED`
4. `IPL_CHUNKING_SEMANTIC_EMBEDDING_MODEL`
5. `IPL_CHUNKING_SEMANTIC_THRESHOLD`
6. `IPL_CHUNKING_SEMANTIC_CHUNK_SIZE`
7. `IPL_CHUNKING_SEMANTIC_SIMILARITY_WINDOW`
8. `IPL_CHUNKING_SEMANTIC_SKIP_WINDOW`
9. `IPL_CHUNKING_IMPRESSION_LIST_MAX_ITEMS_PER_CHUNK`
10. `IPL_CHUNKING_IMPRESSION_LIST_MIN_ITEMS_PER_CHUNK`

## Deferred Idea (Not In Active Scope)
`RadSlumberChunker` remains a possible future experiment for LLM adjudication over semantic candidates. It is explicitly deferred while we optimize throughput and stabilize sentence+semantic chunking behavior.

## Future Ideas Backlog
1. Optional dual-routing for `Findings/Impression`:
   - split into synthetic `findings` + `impression` views, then dedupe at merge.
2. Stronger implicit-findings inference:
   - gate inference with lightweight lexical/rule checks to reduce false positives in unusual layouts.
3. Section alias curation workflow:
   - periodically mine section headers from new corpora and add only frequency-validated radiology variants.
4. Smarter list marker handling:
   - support additional marker families and nested list shapes only if seen in real data and covered by tests.
5. Impression numeric cross-references (deferred):
   - radiology impressions sometimes reference prior list items by number instead of repeating the entity.
   - planned approach is the same scoped-extraction pattern (extract only from target item/chunk, provide adjacent items as reference context).
   - explicitly out of current implementation scope.

## Acceptance Criteria
1. No extraction calls are executed for non-`findings`/`impression` sections.
2. Findings/impression extraction units are chunk-based and parallelized.
3. Jobs remain resilient when semantic chunking fails (sentence fallback).
4. Existing modular extraction tests remain green with updated chunking behavior.
