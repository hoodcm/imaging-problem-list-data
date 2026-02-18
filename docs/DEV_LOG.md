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
5. Updated active plan docs for remaining orchestrator completion phases and future ideas:
   - `docs/extractor-agent-plans/stream-restructure-orchestrator-core.md`
   - `docs/extractor-agent-plans/chunk-extraction-prompt-schema-plan.md`
   - `docs/future-improvements.md` (dynamic example selection backlog item)
