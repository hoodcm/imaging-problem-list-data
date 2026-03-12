# Findings/Impression Chunking Plan (V2 Runtime Contract)

Last updated: 2026-02-16
Status: Active

## Current Policy

1. Deterministic section split runs first.
2. Extraction scope is only `findings` and `impression`.
3. Below sentence-threshold sections are passthrough (single chunk).
4. `impression` uses list-item chunking when list structure is detected.
5. Otherwise semantic chunking is used for larger sections.
6. Headings are excluded from chunk payload text.

## Extraction Chunk Contract

Each extraction chunk includes:

1. section name (`findings` or `impression`)
2. target chunk text (extractable)
3. preceding half-chunk context (advisory)
4. following half-chunk context (advisory)

Extraction must be constrained to evidence from target chunk only.

## Why This Helps

1. smaller chunk-scoped prompts improve throughput
2. bounded parallelism improves end-to-end latency
3. context windows reduce local ambiguity without broadening extraction scope

## Configuration Surface

1. `IPL_CHUNKING_SEMANTIC_TRIGGER_SENTENCE_COUNT`
2. `IPL_CHUNKING_IMPRESSION_LIST_CHUNKING_ENABLED`
3. `IPL_CHUNKING_IMPRESSION_LIST_MAX_ITEMS_PER_CHUNK`
4. `IPL_CHUNKING_IMPRESSION_LIST_MIN_ITEMS_PER_CHUNK`
5. `IPL_CHUNKING_SEMANTIC_EMBEDDING_MODEL`
6. `IPL_CHUNKING_SEMANTIC_THRESHOLD`
7. `IPL_CHUNKING_SEMANTIC_CHUNK_SIZE`
8. `IPL_CHUNKING_SEMANTIC_SIMILARITY_WINDOW`
9. `IPL_CHUNKING_SEMANTIC_SKIP_WINDOW`

## Deferred Ideas

1. RadSlumberChunker / LLM boundary adjudication remains deferred.
2. Impression cross-item reference repair is deferred (future pass with adjacency/context hints).
