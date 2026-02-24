# Agent Restructuring Plan (V2)

Last updated: 2026-02-18
Status: Active

## Purpose

This document is the top-level overview for extractor restructuring.
Detailed implementation specs live in active plan documents under
`docs/extractor-agent-plans/`.

## Canonical Plan Documents

1. `docs/extractor-agent-plans/orchestrator-core-plan.md`:
   orchestrator flow, stage contract, validator loop, timeouts, exam-info lane.
2. `docs/extractor-agent-plans/chunk-extraction-prompt-schema-plan.md`:
   chunk extraction schema/prompt contract and examples.
3. `docs/extractor-agent-plans/finding-and-location-code-assignment-plan.md`:
   deterministic-first code assignment and adjudication behavior.
4. `docs/extractor-agent-roadmap.md`:
   integration order and cross-plan dependency notes.

## Current Execution Path (What We Are Building)

1. `preflight`: validate runtime/model configuration and initialize run state.
2. `sectionize`: deterministic section parse, extract only findings/impression,
   then chunk those sections.
3. `extract_sections`: run chunk extraction sub-agents in bounded parallelism.
4. `exam_info`: run dedicated exam-info extractor in parallel with chunk extraction
   using filename/hints/metadata + report header context.
5. `merge_dedupe`: deterministic assembly and dedupe of chunk outputs.
6. `validator_review`: always run one review pass; allow one targeted re-extract
   cycle with feedback.
7. `validate_output`: run verbatim/coverage validation on final merged output.
8. `persist`: write extraction payload, diagnostics, usage, and stage messages.
9. terminal state: `completed`, `completed_with_warnings`, or `failed`.

Coding (OIFM finding/location code assignment) is a separate, independent tool — see `docs/coding-agent-design.md`.

## Locked Product/Design Decisions

1. Section splitting is deterministic and happens first.
2. Only findings/impression are extraction scopes.
3. Chunk context is advisory only; extraction evidence must come from target chunk.
4. Default sub-agent concurrency is `5`, with bounded async semaphore control.
5. Retry is unit-scoped; no full-report retry path.
6. Code assignment is a separate tool, not part of the extraction pipeline.
7. Stage messages are canonical and machine-parseable (`[stage:<name>] <detail>`).

## Recently Completed

1. Exam-info sub-agent: parallel execution, non-fatal, `ExamInfoExtraction` model.
2. Validator review with per-unit feedback: `ReviewRequest` model, feedback threading.
3. Per-piece timeouts: `subagent_timeout_seconds` config, all sub-agent paths.
4. Code review fixes: context-aware coding cache key, exam-info task cancellation on failure.
5. Renamed `code_assinger.py` → `code_assigner.py`.
6. Active runtime path is chunk-only (`extract_chunk_findings`); legacy full-report helper remains only for non-runtime tests.
7. Decoupled coding from extraction — coding is now an independent tool (see `docs/coding-agent-design.md`). Batch coding pipeline prototyped inline, then stripped; learnings captured in design doc.

## Current Focus

1. Prompt/policy tuning for exam-info and validator review quality.
2. Replace broad `Callable[...]` type aliases with explicit `Protocol` signatures.
3. Build standalone coding agent on `coding-agent` branch.

## Deferred Improvements

1. Replace broad `Callable[...]` type aliases with `Protocol` signatures for type safety.
2. Shared modality enum between `ExamInfoExtraction` and `ExamInfo` to prevent drift.
3. Structured feedback model (beyond string) for richer prompt modifications.
4. Pipeline diagnostics extension with per-stage timing and sub-agent success rates.
