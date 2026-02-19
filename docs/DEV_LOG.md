# Development Log

Older entries through 2026-02-17 are archived in [archive/dev-log-through-2026-02-17.md](archive/dev-log-through-2026-02-17.md).

---

## 2026-02-18 - Documentation cleanup and restructuring

1. Added `docs/README.md` as categorized index of all documentation.
2. Archived 23 completed/historical docs to `docs/archive/`:
   - 12 completed stage/stream docs from `extractor-agent-plans/`
   - 2 one-time artifacts (`ui-improvement-fixes.md`, `ui-impact-runtime-unification.md`)
   - 9 completed plan docs (`testing_plan.md`, `batch-runner-plan.md`, `data-model-plan.md`, `config-plan.md`, `migration-architecture.md`, `api-server.md`, `extractor-frontend.md`, `database-layer.md`, `logging-plan.md`)
3. Updated all cross-references in active docs to point to `archive/` paths.
4. Updated root `README.md` to remove stale doc references.
5. Rotated DEV_LOG.md (121K → fresh start; full history in archive).

## 2026-02-18 — Orchestrator next-phase: exam-info, coding context, validator feedback, timeouts

Implemented all four "Immediate Next Work Items" from the orchestrator core plan:

1. **Exam-info sub-agent** (`exam_info_agent.py`): dedicated agent extracts modality,
   body part, and laterality from the report header. Runs in parallel with chunk
   extraction via `asyncio.create_task`; non-fatal on failure (keeps placeholder).
   Added `laterality` field to `ExamInfo` model.
2. **Coding adjudicator context upgrade** (`coding_agents.py`, `code_assigner.py`):
   adjudication prompts now receive exam info, presence, location fields, and evidence
   text. Cache key includes exam context to prevent cross-report stale hits.
   Renamed `code_assinger.py` → `code_assigner.py` (typo fix).
3. **Validator review with feedback** (`extraction_review.py`, `extraction_orchestrator.py`):
   `ReviewRequest` model carries per-unit feedback and suspected_issue. Feedback is
   threaded to retry units and appended to chunk extraction prompts. Default changed
   to `validator_review_enabled=True`.
4. **Per-piece timeouts** (`config.py`, `extraction_orchestrator.py`):
   `subagent_timeout_seconds` (default 20s) wraps chunk extraction, coding, validator
   review, and exam-info await. All timeout paths are non-fatal except chunk extraction
   (which feeds into existing repair logic).

Bug fixes from code review:
- Coding cache key now includes exam context fields and evidence text to prevent stale adjudication reuse.
- Exam-info task is cancelled on early orchestrator failure (all chunks fail).

Test coverage: 15 new/updated orchestrator tests covering parallel exec, timeouts,
feedback threading, non-fatal failures. 60 tests passing across affected modules.

## 2026-02-18 - Chunk sub-agent wiring + model guidance docs

1. Wired orchestrator chunk-unit extraction calls to the dedicated chunk prompt/schema path:
   - runtime/worker now use `extract_chunk_findings` for unit extraction
   - chunk context fields (`section_name`, prev/next context) are passed explicitly
2. Kept final assembled contract unchanged (`ReportExtraction`) while adapting chunk payloads.
3. Updated extraction docs to reflect chunk sub-agent behavior:
   - `docs/extraction-internals.md`
   - `docs/extraction-usage.md`
4. Added model guidance reference:
   - `docs/model-selection-notes.md`
5. Updated active plan docs for remaining orchestrator work and future ideas:
   - `docs/extractor-agent-plans/orchestrator-core-plan.md`
   - `docs/extractor-agent-plans/chunk-extraction-prompt-schema-plan.md`
   - `docs/future-improvements.md` (dynamic example selection backlog item)
