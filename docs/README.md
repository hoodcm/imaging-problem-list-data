# Documentation Index

## Reference — How Things Work Now

### Extraction
- [extraction-usage.md](extraction-usage.md) — CLI usage, model selection, multi-provider examples
- [extraction-internals.md](extraction-internals.md) — Runtime module map and orchestrator flow
- [model-selection-notes.md](model-selection-notes.md) — Current model defaults and chunk-extraction model guidance
- [report-sections.md](report-sections.md) — Report sectioning and semantic chunking patterns

### API & Backend
- [api-usage.md](api-usage.md) — API endpoint reference for consumers
- [api-internals.md](api-internals.md) — API/worker module architecture for maintainers
- [dev-ops.md](dev-ops.md) — Docker Compose topology and operational setup
- [schema-migrations.md](schema-migrations.md) — Alembic operational runbook

### Configuration
- [configuration.md](configuration.md) — Canonical env var reference and precedence

### Persistence
- [persistence-usage.md](persistence-usage.md) — ExtractionStore API for callers
- [persistence-internals.md](persistence-internals.md) — SQLModel/SQLite schema and connection setup

### Evaluation
- [eval-usage.md](eval-usage.md) — Evaluation CLI reference and CI gate examples
- [eval-internals.md](eval-internals.md) — Evaluation harness architecture and matching algorithm

### Frontend
- [frontend-usage.md](frontend-usage.md) — Extractor UI views and features
- [frontend-internals.md](frontend-internals.md) — Extractor UI code structure
- [ipl-frontend-guide.md](ipl-frontend-guide.md) — Project-specific frontend conventions (both SPAs)

### Logging
- [logging-usage.md](logging-usage.md) — Runtime logging controls for operators
- [logging-internals.md](logging-internals.md) — Logging implementation for contributors

### Testing
- [testing-practices.md](testing-practices.md) — Project-specific testing conventions

### Workflows
- [human-review-workflow.md](human-review-workflow.md) — Creating gold extractions from sample data

## Active Plans

- [agent-restructuring.md](agent-restructuring.md) — V2 orchestrator master plan (locked decisions, runtime flow)
- [extractor-agent-roadmap.md](extractor-agent-roadmap.md) — V2 roadmap, active workstreams, merge strategy
- [semantic-chunking-plan.md](semantic-chunking-plan.md) — Chunking policy and V2 extraction unit contract
- [viewer-refactoring.md](viewer-refactoring.md) — Viewer CDN/Tailwind migration plan
- [extractor-agent-plans/](extractor-agent-plans/) — Active implementation streams (see its [README](extractor-agent-plans/README.md))

## Backlogs

- [pending-refactoring.md](pending-refactoring.md) — Near-term refactoring/cleanup queue
- [future-improvements.md](future-improvements.md) — Longer-horizon improvement backlog

## Work Log

- [DEV_LOG.md](DEV_LOG.md) — Chronological development log with milestone evidence

## Archive

- [archive/](archive/) — Completed plans, historical artifacts, and rotated logs
