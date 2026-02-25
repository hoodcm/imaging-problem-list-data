# Future Improvements Backlog

Last updated: 2026-02-24
Status: Active

This is the centralized longer-horizon improvement backlog.

## Candidate Improvements

| ID | Priority | Item | Origin |
|---|---|---|---|
| FI-001 | medium | Stream extraction progress to clients (SSE/WS) as an alternative to polling-only job status. | imported from former `docs/code-review-2026-02-15.md` |
| FI-002 | low | Re-evaluate PydanticAI Graph API once stable for orchestrator-state modeling. | imported from former `docs/code-review-2026-02-15.md` |
| FI-003 | low | Add explicit stage-level OpenTelemetry/Logfire spans for orchestrator timing breakdowns. | imported from former `docs/code-review-2026-02-15.md`; aligns with `docs/logging-internals.md` |
| FI-004 | medium | Revisit semantic boundary quality with LLM boundary-adjudication chunking (RadSlumber-style direction). | `docs/semantic-chunking-plan.md` |
| FI-005 | medium | Add impression cross-item reference repair for numbered/bulleted cross-references. | `docs/semantic-chunking-plan.md` |
| FI-006 | medium | Viewer modernization follow-up (Tailwind v4/Flowbite 4.0.1 alignment + Alpine dark-mode cleanup). | `docs/viewer-refactoring.md` |
| FI-007 | low | Optional batch-runner backend mode using API/TaskIQ while preserving current CLI UX contract. | `docs/archive/batch-runner-plan.md` |
| FI-008 | low | Evaluate two-layer persistence/API read-schema consolidation (remove intermediate dataclass mapping layer). | `docs/archive/data-model-plan.md` |
| FI-009 | low | Logging refinements: access-log normalization, context-propagation edge cases, and log-volume controls when justified by operations. | `docs/logging-internals.md` |
| FI-010 | low | Reduce config alias boilerplate using structured/nested settings and `env_prefix` patterns where safe. | `docs/extractor-agent-roadmap.md` |
| FI-011 | medium | Expand chunk-example library and add dynamic, chunk-aware example selection for prompt assembly (rather than fixed first-N examples). | extraction prompt/schema workstream |
| FI-012 | low | Test coding agent independently against fixture extractions — the clean decoupling enables this without running the extraction pipeline. | coding decoupling review |

## Archive Candidates

Moved to `docs/archive/` on 2026-02-18:

1. ~~`docs/testing_plan.md`~~ — archived (PR-016 stays in backlog)
2. ~~`docs/batch-runner-plan.md`~~ — archived (FI-007 stays in backlog)
3. `docs/viewer-refactoring.md` — kept active (FI-006 modernization still in progress)
4. ~~`docs/data-model-plan.md`~~ — archived (FI-008 stays in backlog)
5. ~~`docs/logging-plan.md`~~ — archived

Also archived: `config-plan.md`, `migration-architecture.md`, `api-server.md`, `extractor-frontend.md`, `database-layer.md`.

## Intake Rules

- Keep immediate refactor work in `docs/pending-refactoring.md`.
- Keep only non-immediate improvements here.
- When an improvement becomes active work, move it into the pending refactoring queue.
