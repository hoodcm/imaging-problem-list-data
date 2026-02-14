# Legacy Doc Capture Audit Done

Captured on: 2026-02-14

## Purpose

Confirm that documentation from the previous split attempt was preserved and mapped, not lost.

## Backup location (pre-delete safety copy)

Legacy docs were moved (not deleted) to:
1. `/tmp/extractor-agent-doc-cleanup-20260214-044157/`

Contents there:
1. `extractor-agent-plan.md` (previous pointer doc)
2. `plans/README.md`
3. `plans/extractor-roadmap.md`
4. `plans/eval-quality-gates.md`
5. `plans/extraction-reliability.md`
6. `plans/coding-bridge-oifm.md`
7. `plans/extractor-roadmap-completed-2026Q1.md`

## Mapping to current canonical docs

1. `plans/extractor-roadmap.md` -> `docs/extractor-agent-roadmap.md`
2. `plans/eval-quality-gates.md` -> stream coverage in `docs/extractor-agent-plans/stream-eval-closure.md`
3. `plans/extraction-reliability.md` -> `docs/extractor-agent-plans/stream-reliability-contract.md`
4. `plans/coding-bridge-oifm.md` -> `docs/extractor-agent-plans/stream-coding-bridge.md`
5. `plans/extractor-roadmap-completed-2026Q1.md` -> decomposed into stage-specific `*_done.md` files in `docs/extractor-agent-plans/`

## Result

Current canonical planning set is in:
1. `docs/extractor-agent-roadmap.md`
2. `docs/extractor-agent-plans/`

Legacy snapshot remains available under `/tmp` for verification before any permanent deletion.
