# Stream Eval Closure: Stage 3 Report-Section Improvements (Eval Evidence)

Last updated: 2026-02-15
Status: **Closed** — accepted, no material regression

## Stage definition

Stage 3 here means: validate the already-implemented report-section parsing + `source_section` guidance changes with explicit measured eval evidence.

## Why this stream exists

Implementation landed, but closure is incomplete until before/after evidence is recorded and reviewed.

## Scope

1. Run baseline and candidate `eval:comprehensive` comparisons for Stage 3 parser/prompt changes.
2. Record run IDs, metric deltas, and pass/fail decision in `docs/DEV_LOG.md`.
3. Update roadmap status from "implemented" to "closed" when evidence is accepted.

## Out of scope

1. New prompt experiments unrelated to Stage 3 closure.
2. New output schema changes.

## Execution checklist

1. [x] Select baseline run/commit and current-candidate run/commit.
2. [x] Execute `task eval:comprehensive` for both.
3. [x] Compare with `finding-extractor-eval report <candidate> --compare <baseline>`.
4. [x] Validate against existing threshold policy.
5. [x] Publish a closure note with concrete metrics and dates.

## Acceptance criteria

1. [x] Evidence is documented with run IDs and metric deltas.
2. [x] No material regression in critical metrics (`finding_f1`, `presence_accuracy`, `verbatim_pass`).
3. [x] Roadmap and stream status updated to closed.

## Evidence

### Run configuration

| Parameter | Candidate | Baseline |
|-----------|-----------|----------|
| Model | `openai:gpt-5-mini` | `openai:gpt-5-mini` |
| Reasoning | `medium` | `medium` |
| Workers | 2 | 2 |
| Retries | 0 | 1 |
| Timeout | 120s | 120s |
| Dataset | `comprehensive` (9 cases) | `comprehensive` (9 cases) |

### Runs

| Run | Run ID | Commit | Cases completed |
|-----|--------|--------|-----------------|
| Baseline (pre-Stage 3) | `baseline-pre-stage3` | `815fdb1` | 5/9 (4 timeouts) |
| Candidate (Stage 3 + merges) | `eval-20260215-103012-ad5468da` | `03ea0e2` | 7/9 (2 timeouts) |

**Common cases** (4): `ct_abdomen_20210826`, `ct_abdomen_20251007`, `mr_brain_20230125`, `xr_shoulder_20210522`

### Critical metric comparison (common cases, candidate vs baseline)

| Metric | Candidate | Baseline | Delta | Verdict |
|--------|-----------|----------|-------|---------|
| `finding_f1` | 0.950 | 0.946 | +0.004 | No regression |
| `presence_accuracy` | 0.983 | 0.950 | +0.033 | Improved |
| `verbatim_pass` | 4/4 (100%) | 4/4 (100%) | 0 | No regression |
| `verbatim_rate` | 1.00 | 1.00 | 0 | No regression |

### Full metric comparison (common cases, candidate vs baseline)

| Metric | Candidate | Baseline | Delta |
|--------|-----------|----------|-------|
| `finding_precision` | 0.942 | 0.920 | +0.022 |
| `finding_recall` | 0.963 | 0.976 | -0.013 |
| `finding_f1` | 0.950 | 0.946 | +0.004 |
| `presence_accuracy` | 0.983 | 0.950 | +0.033 |
| `body_region_accuracy` | 0.992 | 0.993 | -0.001 |
| `laterality_accuracy` | 1.000 | 1.000 | 0 |
| `attribute_precision` | 0.750 | 0.717 | +0.033 |
| `attribute_recall` | 0.753 | 0.731 | +0.022 |
| `verbatim_rate` | 1.000 | 1.000 | 0 |
| `nonfinding_category_accuracy` | 1.000 | 1.000 | 0 |

### Per-case finding F1

| Case | Candidate | Baseline | Delta |
|------|-----------|----------|-------|
| `ct_abdomen_20210826` | 0.984 | 0.984 | 0 |
| `ct_abdomen_20251007` | 0.939 | 0.958 | -0.019 |
| `mr_brain_20230125` | 0.967 | 0.933 | +0.034 |
| `xr_shoulder_20210522` | 0.909 | 0.909 | 0 |

### Additional candidate-only cases (not in baseline due to timeouts)

| Case | finding_f1 | presence_accuracy | verbatim_pass |
|------|-----------|-------------------|---------------|
| `ct_abdomen_20230118` | 0.907 | 1.000 | pass |
| `us_abdomen_20220208` | 0.957 | 1.000 | pass |
| `xr_chest_20210614` | 1.000 | 0.955 | pass |

### Limitations

- **4/9 case overlap.** API timeouts reduced both runs; only 4 cases are directly comparable. The 120s timeout is tight for some comprehensive cases with `medium` reasoning.
- **Single-run comparison.** LLM outputs are non-deterministic; results may vary across runs.
- **Retries differ.** Baseline used `retries=1` (retrying failed cases, doubling max wall time), candidate used `retries=0`. This likely explains much of the timeout count difference (4 vs 2), not prompt-level latency changes.

## Decision

**ACCEPTED.** No material regression on any critical metric across the 4 common cases. The candidate shows small improvements in `finding_f1` (+0.004), `presence_accuracy` (+0.033), and attribute metrics. All thresholds passed (`finding_f1` >= 0.5, `presence_accuracy` >= 0.7, `verbatim_pass` = 100%).

Stage 3 is closed.
