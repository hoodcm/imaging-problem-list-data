# Finding Extractor Internals

Architecture notes for contributors working on the extraction runtime.

Last verified against code: 2026-02-26 (`agent-refactor`)

## Module Map

| File | Role |
|---|---|
| `src/finding_extractor/extractor/runtime.py` | Shared entrypoint for worker/CLI/batch/eval; preflight, orchestrator wiring, reliability policy, optional persistence |
| `src/finding_extractor/extractor/orchestrator.py` | Chunk-scoped orchestration and status emission |
| `src/finding_extractor/extractor/agent.py` | Chunk sub-agent (`extract_chunk_findings` / `extract_chunk`) with dedicated chunk prompt/schema; legacy full-report helper retained for non-runtime tests |
| `src/finding_extractor/semantic_chunking.py` | Findings/impression chunking policy (sentence-first, semantic grouping, impression list chunking) |
| `src/finding_extractor/impression_list_chunker.py` | Chonkie `BaseChunker` for deterministic impression list-item grouping |
| `src/finding_extractor/report_sections.py` | Deterministic section parsing for radiology reports, including implicit findings inference |
| `src/finding_extractor/extractor/exam_info_agent.py` | Dedicated sub-agent for extracting exam metadata (study_date, modality, body_region, body_part, contrast, laterality) |
| `src/finding_extractor/extractor/review.py` | Validator review pass requesting targeted chunk re-extraction with feedback |
| `src/finding_extractor/tasks.py` | Worker lifecycle and job-state transitions, delegates execution to `run_extraction_runtime()` |

## Canonical Runtime Contract

All extraction surfaces call the same runtime path:

1. worker task (`tasks.py`)
2. CLI (`cli.py`)
3. batch CLI (`batch_cli.py`)
4. eval task adapter (`eval/task.py`)

That shared path is `run_extraction_runtime()`, which always calls `run_orchestrated_extraction()`.

## End-to-End Pipeline (Current)

```mermaid
sequenceDiagram
    autonumber
    participant U as User/Client
    participant API as FastAPI
    participant ST as ExtractionStore
    participant Q as TaskIQ/Redis
    participant WK as Worker Task
    participant RT as extraction_runtime
    participant OR as extraction_orchestrator
    participant AG as extraction_agent(chunk)
    participant EI as exam_info_agent

    U->>API: POST /api/reports
    API->>ST: upsert_report(report_text)
    ST-->>API: report_id

    U->>API: POST /api/reports/{id}/extract
    API->>ST: create_job(status=pending)
    API->>Q: enqueue run_extraction(job_id, report_id,...)
    API-->>U: 202 + Location:/api/jobs/{job_id}

    Q->>WK: run_extraction task
    WK->>ST: mark_job_running + stage status updates
    WK->>RT: run_extraction_runtime(...)
    RT->>OR: run_orchestrated_extraction(...)

    OR->>OR: sectionize (findings/impression chunks)
    OR->>OR: semantic/list chunk expansion
    par chunk extraction + exam info (bounded concurrency)
        OR->>EI: extract_exam_info(report_text)
        OR->>AG: extract_chunk_findings(chunk_1 + context)
        AG-->>OR: extraction_1
    and
        OR->>AG: extract_chunk_findings(chunk_n + context)
        AG-->>OR: extraction_n
    end

    OR->>OR: repair failed chunks (optional)
    OR->>OR: merge + dedupe
    EI-->>OR: exam_info (update extraction)
    OR->>OR: validator review + targeted reextract with feedback
    OR->>OR: validate output (optional)
    OR-->>RT: final ReportExtraction + diagnostics

    RT->>ST: create_extraction(...) (if persistence enabled)
    WK->>ST: mark completed/completed_with_warnings/failed
    ST-->>API: job status rows
    U->>API: GET /api/jobs/{job_id}
    API-->>U: status + status_event + extraction_id/error
```

## Stage Status Sequence

The runtime stack emits parseable stage messages as:

`[stage:<stage_name>] <detail>`

Canonical stages and ownership:

1. `preflight` (runtime)
2. `sectionize` (orchestrator)
3. `extract_exam_info` (orchestrator, parallel with chunk extraction)
4. `extract_sections` (orchestrator)
5. `repair_failed_sections` (orchestrator)
6. `merge_dedupe` (orchestrator)
7. `validator_review` (orchestrator)
8. `validate_output` (orchestrator)
9. `persist` (runtime, when storage enabled)
10. `completed` (runtime)
11. `completed_with_warnings` (runtime)
12. `failed` (worker task failure path)

Worker callbacks persist these to `jobs.status_message`; API maps them into `status_event`.

## Sectioning and Chunking Behavior

Sectioning:

1. deterministic regex header detection (`findings`, `impression`, `technique`, etc.)
2. supports aliases like `body` -> `findings`, `conclusion` -> `impression`
3. if no explicit findings header exists, infers an implicit findings block immediately before first impression when plausible
4. extraction proceeds only on `findings` and `impression` sections

Chunking:

1. strip leading section heading text from chunk payloads
2. compute sentence spans first
3. if sentence count is below threshold, passthrough as one chunk
4. impression: if list structure exists, chunk deterministically by grouped list items
5. otherwise semantic grouping (Chonkie `SemanticChunker`) with sentence-group fallback on semantic failure
6. enforce max sentences per final chunk (default 3)

See `docs/semantic-chunking-plan.md` for tuning details.

## Extraction Chunk Contract

Each chunk includes:

1. `section_name` (`findings` or `impression`)
2. target chunk text
3. preceding half-chunk context
4. following half-chunk context

The chunk sub-agent enforces a dedicated `ChunkExtraction` schema and constrains
evidence to target chunk text; adjacent context is advisory.

## Coding

Coding (OIFM finding code and anatomic location code assignment) is a separate, independent tool — not part of the extraction pipeline. See `docs/coding-agent-design.md`.

## Validator Review Contract

Validator review runs by default in the V2 runtime. Config controls:

1. `IPL_VALIDATOR_REVIEW_ENABLED` (default: `true`)
2. `IPL_VALIDATOR_MODEL` (optional override; must differ from extraction model)
3. `IPL_VALIDATOR_REASONING`
4. `IPL_VALIDATOR_REEXTRACT_ENABLED`

When enabled, review produces one `ExtractionReviewDecision` per chunk with:
- `report_chunk_id`: chunk being reviewed
- `should_reextract`: whether that chunk should be re-run
- `problems[]`: validator-identified issues (`raw_extracted_finding_index`, `extract_problem_type`, `problem_detail`)
- `rationale`: optional reviewer explanation

Feedback is threaded to retry chunks and appended to the chunk extraction prompt.
Review timeout is non-fatal — pipeline continues without re-extraction.

## Reasoning Compatibility Contract

Runtime resolves reasoning levels for extraction and validator model calls before
any provider request:

1. resolve requested level (explicit -> config default -> provider default)
2. apply known-safe normalization for model-specific incompatibilities
3. fail fast when model-family compatibility cannot be verified

The default behavior is strict fail-fast for unknown model families. This can be
overridden with `IPL_ALLOW_UNKNOWN_MODEL_REASONING=true`.

This runtime-compatible resolver is used consistently in worker/API/CLI batch/eval
preflight paths to avoid entrypoint-specific behavior drift.

## Reliability and Terminal Outcomes

Runtime warning payloads capture validation/verbatim/coverage/section-failure categories.

1. strict mode fails on validation failures or unrecovered section failures
2. lenient mode can complete with warnings
3. terminal statuses are machine-parseable: `completed`, `completed_with_warnings`, `failed`

## Testing Pointers

Primary coverage for runtime and orchestration behavior:

1. `tests/test_extraction_orchestrator.py`
2. `tests/test_semantic_chunking.py`
3. `tests/test_impression_list_chunker.py`
4. `tests/test_extraction_runtime.py`
5. `tests/test_tasks.py`
6. `tests/test_exam_info_agent.py`
7. `tests/test_extraction_review.py`
