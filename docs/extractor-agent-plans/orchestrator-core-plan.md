# Orchestrator Core Plan (V2)

Last updated: 2026-02-23
Status: In progress

## Goal

Ship one orchestrator runtime path that is chunk-native, parallel, deterministic in assembly, and reviewable via structured status events.

## Scope

1. Replace legacy/modular split with V2 core flow.
2. Build chunk extraction units from findings/impression sections only.
3. Add context-window contract per chunk (prev/next half chunks).
4. Run extraction sub-agents with bounded semaphore concurrency (`default=5`).
5. Add unit-scoped retry and validator-guided targeted re-extraction.
6. Keep deterministic merge/dedupe and stable ordering.

## Completed Work Items (2026-02-18)

All four user-directed items are implemented and tested.

1. ~~Add a dedicated exam-info sub-agent that runs in parallel with chunk extraction.~~ Done: `exam_info_agent.py`, parallel via `asyncio.create_task`, non-fatal.
2. ~~Upgrade coding adjudication prompts to use finding context + strict unresolved behavior.~~ Done: prototyped as batch per-chunk coding pipeline, then decoupled from extraction into standalone coding agent (see `docs/coding-agent-design.md`).
3. ~~Make validator review non-optional and enable feedback-based targeted re-extraction.~~ Done: `extraction_review.py` + orchestrator; review always runs, `ReviewRequest` model carries per-unit feedback.
4. ~~Add per-piece timeouts (target: 20s) for chunk extraction, coding adjudication, validator review, and exam-info extraction.~~ Done: `subagent_timeout_seconds` config (default 20s), wraps all sub-agent calls.

## Draft Prompts (Editable)

These are draft prompt blocks for review/edit before implementation.

### Draft Prompt: Exam Info Extractor

```
```
System prompt:

You examine a radiology report and determine basic information about it, such as what kind of exam it was.

Rules:
1. Return only metadata that is explicitly present or strongly implied by standard radiology naming.
2. Do not invent dates, modality, or body part.
3. If uncertain, return null for that field.
4. Prefer concise normalized values for modality/body part/laterality.
```
```

User payload template:
- File name (may have hints)
- Optional exam description hint.
- Full report text.

`ResponseModel` should be Pydantic `BaseModel` with definite types, including `Enum` or `Literal` for modality; all are optional. All fields should have clear but CONCISE descriptions as part of the field definitions.

### Draft Prompt: Coding Adjudicator (Finding + Location)

```
```
System prompt:

You are an expert at assigning standard radiology terms and codes to radiology findings to enable similar findings to be associated with one another even if they are described using different language.

Choose exactly one candidate only when it is a clinically credible match.
If there is meaningful ambiguity or mismatch, return unresolved.
Never invent candidate IDs.

Rules:
1. Use exam type, finding name, presence, location context, and evidence text.
2. Respect anatomy/laterality compatibility.
3. Prefer unresolved over weak matches.
4. Return only selected candidate ID from list, or unresolved.
5. If there is a candidate location or finding representing a SLIGHTLY more general match to what you had in mind, you can use the more general type.
6. Do NOT offer a more SPECIFIC or LOCALIZED version of the body part or finding, do NOT offer that as a match
7. If you CANNOT find a match, saw what you think the canonical name of the location or finding that you WOULD confidently choose as a match
```
```

User payload template:
- exam information (modality, body part, laterality)
- finding_name
- presence
- location fields
- evidence quote
- candidate list

`ResponseModel` should be Pydantic `BaseModel` with definite types, including `Enum` or `Literal` for modality; all are optional. All fields should have clear but CONCISE descriptions as part of the field definitions.

### Draft Prompt: Validator Review with Feedback

System prompt:

```
```
You review merged chunk-level extraction output for missed or inconsistent findings.
If you see that a particular extraction of a finding description from the report text does not follow the rules, request re-extraction with concrete evidence and guidance for re-extraction.
Return minimal targeted requests.

Rules:
1. Only reference provided unit labels.
2. Provide short actionable feedback per requested unit.
3. Do not request broad reruns.
4. Prefer precision over recall.
```
```

Make sure to include a copy of the rules that were given to the chunk extractor sub-agent so the validator knows what the extractions were going for.

Output schema:
- should_reextract: bool
- requests: list of
  - unit_label: string
  - feedback: string
  - suspected_issue: short string
- rationale: string or null

`ResponseModel` should be Pydantic `BaseModel` with definite types, including `Enum` or `Literal` for modality; all are optional. All fields should have clear but CONCISE descriptions as part of the field definitions.

User payload template:
- report preview
- unit summaries (label, section, preview, context flags)
- merged finding summaries

## Required Stage Vocabulary

1. `preflight`
2. `sectionize`
3. `extract_exam_info`
4. `extract_sections`
5. `repair_failed_sections`
6. `merge_dedupe`
7. `validator_review`
8. `validate_output`
9. `persist`
10. `completed`
11. `completed_with_warnings`
12. `failed`

## Implementation Outline

1. `extraction_orchestrator.py`
   1. define V2 unit models (`chunk_id`, section, target text, context windows)
   2. build units from deterministic section parser + chunker
   3. run bounded async extraction with retries
   4. merge/dedupe deterministically
   5. run validator and targeted retry pass
2. `extraction_agent.py`
   1. add chunk-focused prompt contract with context channels
   2. maintain verbatim validation against target chunk only
3. `tasks.py`
   1. wire V2 orchestrator parameters and status event emission

## Test Focus

1. chunk unit generation and context windows
2. bounded concurrency and retry behavior
3. deterministic merge order under async completion variance
4. validator-driven targeted re-extraction behavior

## Verification Checklist (Must Pass)

Each item below must be proven with either automated tests or a reproducible smoke run artifact.

1. Section detection handles implicit findings, combined findings/impression headers, and impression-only reports.
2. Section heading stripping works and chunk boundaries preserve full section text coverage.
3. Prev/next context windows are attached correctly and never treated as extraction evidence.
4. Extraction callable contract is explicit and enforced (no silent kwarg dropping).
5. Unit retry logic retries only failed units and reports attempt counts correctly.
6. Validator-triggered re-extraction updates failed-unit diagnostics correctly.
7. Merge/dedupe keeps deterministic ordering and correct `source_section` resolution.
8. `non_finding_text` behavior is explicitly decided and validated in tests.
9. ~~Inline coding aligns correctly to merged findings.~~ No longer applicable — coding is decoupled.
10. Strict/lenient reliability behavior and warning payload categories are correct.
11. Stage status events are machine-parseable and consistently emitted across runtime paths.
12. Expected retryable failures do not flood user-facing output with raw stack traces.
13. Model/fallback/reasoning behavior matches provider constraints and preflight policy.
14. Persistence writes correct job/extraction status, usage, and status event mapping.

## Remaining Cleanup

- replace broad callable aliases with explicit `Protocol` signatures:
- extraction callable
- validator-review callable
- normalize callback/helper naming:
- keep one canonical status-callback type alias
- converge `_emit_stage`/`_emit` helper usage
- remove minor helper duplication:
- reuse semantic chunking single-chunk helper instead of local passthrough helper
- dedupe `_review_chunks` callback wiring between worker/runtime where possible
- move provider-specific reasoning workaround out of runtime and into provider settings resolution

## Completion Plan (Next Execution Order)

### Done

1. ~~Wire orchestrator chunk sub-agent calls to dedicated chunk prompt/schema (`ChunkExtraction`).~~
2. ~~Exam-info sub-agent, coding context upgrade, validator feedback, per-piece timeouts.~~

### Next

1. Remove remaining full-report extraction prompt dependency from orchestrator flow.
2. Replace broad `Callable[...]` type aliases with explicit `Protocol` signatures.
3. Re-run smoke + integration checks against running stack.

### Later

1. Tune chunk example selection policy (fixed deterministic subset vs dynamic selection).
2. Finalize docs for operator-facing model choices and chunk-agent behavior.
3. Shared modality enum between `ExamInfoExtraction` and `ExamInfo` models.
