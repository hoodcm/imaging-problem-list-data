# Evaluation Harness — User Guide

## Overview

The evaluation harness measures extraction quality across prompt, model, and configuration changes. It runs a set of radiology reports through the extraction agent, compares outputs against ground truth, and reports scores across multiple dimensions.

## Quick Start

Run the smoke dataset (2 cases, fast):

```bash
task eval:smoke
```

Or call the CLI directly with custom settings:

```bash
uv run --env-file .env finding-extractor-eval run \
  --dataset smoke \
  --model openai:gpt-5-mini \
  --reasoning medium \
  --workers 2
```

## CLI Reference

### `finding-extractor-eval run`

Run evaluation on a dataset and report scores.

| Flag | Default | Description |
|------|---------|-------------|
| `--dataset` | `smoke` | Dataset name (resolved from `evals/datasets/`) or path to YAML file |
| `--model` | settings default | Model identifier (e.g., `openai:gpt-5-mini`, `anthropic:claude-sonnet-4-5`) |
| `--reasoning` | None | Reasoning level: `none`, `minimal`, `low`, `medium`, `high` |
| `--workers` | 2 | Concurrent case workers (1–16) |
| `--timeout-seconds` | 120 | Per-case timeout in seconds |
| `--run-id` | auto-generated | Custom run identifier |
| `--run-dir` | `.eval_runs` | Directory for run results |
| `--retries` | from settings | Per-case retries on transient failure (0–5) |
| `--threshold-f1` | — | Minimum `finding_f1` score; exit non-zero if below |
| `--threshold-presence` | — | Minimum `presence_accuracy` score; exit non-zero if below |
| `--threshold-verbatim` | off | Require all verbatim checks to pass (`verbatim_pass >= 1.0`) |

### Example: CI Quality Gate

```bash
finding-extractor-eval run \
  --dataset smoke \
  --model openai:gpt-5-mini \
  --reasoning medium \
  --threshold-f1 0.5 \
  --threshold-presence 0.7 \
  --threshold-verbatim
```

Exit code is 0 if all thresholds pass, 1 if any fail.

### Example: Compare Models

```bash
# Run A
finding-extractor-eval run --dataset smoke --model openai:gpt-5-mini --reasoning medium --run-id run-a
# Run B
finding-extractor-eval run --dataset smoke --model anthropic:claude-sonnet-4-5 --reasoning medium --run-id run-b
# Compare
finding-extractor-eval report run-a --compare run-b
```

### `finding-extractor-eval import-baseline`

Import reviewed batch extraction results as ground truth eval cases.

| Flag | Default | Description |
|------|---------|-------------|
| `SOURCE_DIR` (argument) | — | Directory containing report text + `.extracted.json` pairs |
| `--dataset` | (required) | Target dataset name (e.g., `comprehensive`) or path to YAML file |
| `--glob` | `*.txt` | Glob pattern for report files |
| `--output-suffix` | `.extracted.json` | Suffix convention for extraction files |
| `--append / --no-append` | `--append` | Append to existing dataset or overwrite |
| `--source-label` | directory basename | Label for `source_file` metadata |
| `--model-filter` | — | Only import extractions from a specific model |

### Example: Import Baseline Workflow

```bash
# 1. Run batch extraction on sample reports
finding-extractor-batch run sample_data/example2 --glob "*.md" --validate --model openai:gpt-5-mini

# 2. Human reviews *.extracted.json files, fixes any errors

# 3. Import as ground truth
finding-extractor-eval import-baseline sample_data/example2 \
  --dataset comprehensive --glob "*.md" --output-suffix .extracted.json
```

### `finding-extractor-eval report`

View results from a previous eval run, optionally comparing two runs.

| Flag | Default | Description |
|------|---------|-------------|
| `RUN_ID` (argument) | latest | Run ID to display. If omitted, shows latest run. |
| `--compare` | — | Second run ID for side-by-side comparison |
| `--run-dir` | from settings | Directory containing run results |

### Example: View and Compare Runs

```bash
# Show latest run
finding-extractor-eval report

# Show specific run
finding-extractor-eval report eval-20260212-100000-abc12345

# Compare two runs
finding-extractor-eval report run-a --compare run-b
```

The comparison table shows:
- Metric name, Run A value, Run B value, delta, direction arrow
- Improvements in green (arrow up), regressions in red (arrow down)
- Per-case F1 breakdown with deltas

## Taskfile Commands

```bash
task eval:smoke                          # smoke dataset (2 cases, fast, CI-safe)
task eval:comprehensive                  # comprehensive dataset (10 cases, ~5 min)
MODEL=anthropic:claude-sonnet-4-5 task eval:smoke   # override model
WORKERS=4 task eval:smoke                # increase parallelism
```

## Interpreting Results

The harness reports scores across 6 dimensions:

| Metric | Range | What It Measures |
|--------|-------|-----------------|
| `finding_precision` | 0–1 | Fraction of extracted findings that match ground truth |
| `finding_recall` | 0–1 | Fraction of ground truth findings that were extracted |
| `finding_f1` | 0–1 | Harmonic mean of precision and recall |
| `presence_accuracy` | 0–1 | Accuracy of present/absent/possible classification on matched findings |
| `body_region_accuracy` | 0–1 | Body region correctness on matched findings |
| `laterality_accuracy` | 0–1 | Laterality correctness on matched findings (only when expected) |
| `attribute_precision` | 0–1 | Fraction of extracted attributes that match expected |
| `attribute_recall` | 0–1 | Fraction of expected attributes that were extracted |
| `verbatim_pass` | 0 or 1 | 1.0 if all extracted text is verbatim from the report |
| `verbatim_rate` | 0–1 | Fraction of extracted text segments that are verbatim |
| `nonfinding_category_accuracy` | 0–1 | Accuracy of non-finding text classification (technique, history, etc.) |

## Run Output

Each run produces a directory under `--run-dir` (default `.eval_runs/`):

```
.eval_runs/<run_id>/
  run_config.json    # Frozen run configuration
  results.json       # Aggregate averages + per-case scores
  results.jsonl      # One JSON line per case (for scripted analysis)
```

## Datasets

### Dataset Tiers

| Dataset | Cases | Purpose | Command |
|---------|-------|---------|---------|
| `smoke` | 2 | Fast CI gate, regression detection | `task eval:smoke` |
| `comprehensive` | 10 | Full diversity check, model comparison | `task eval:comprehensive` |

### `smoke` — CI Gate

Two cases from the project's few-shot examples:
- **ct_abdomen_pelvis** — CT abdomen/pelvis without contrast (13 findings)
- **xr_chest** — Chest radiograph PA and lateral (12 findings)

Located at `evals/datasets/smoke.yaml`.

### `comprehensive` — Full Diversity Check

Nine cases covering multiple modalities and body regions:
- CT abdomen (4 cases) — longitudinal same-patient series
- MR brain (1 case) — different modality, different finding types
- US abdomen (1 case) — non-cross-sectional modality
- XR chest (2 cases) — plain film, different patients
- XR shoulder (1 case) — extremity exam

Located at `evals/datasets/comprehensive.yaml`. Imported from `sample_data/example2/` via `import-baseline`.

### Adding Cases

1. Create or edit a YAML file in `evals/datasets/`.
2. Follow the `smoke.yaml` structure: each case has `name`, `inputs` (report_text), `expected_output` (ReportExtraction format), and optional `metadata`.
3. The `expected_output` uses the native `ReportExtraction` schema — the same structure the extractor produces. See `evals/datasets/smoke.yaml` for a complete example.
4. Run the eval to validate: `finding-extractor-eval run --dataset your_dataset`
5. Or use `import-baseline` to import from batch extraction results (see above).

## Configuration

Eval settings can be configured via environment variables or `config.toml`:

| Setting | Env Var | Default |
|---------|---------|---------|
| `eval_run_dir` | `IPL_EVAL_RUN_DIR` | `.eval_runs` |
| `eval_workers` | `IPL_EVAL_WORKERS` | `2` |
| `eval_timeout_seconds` | `IPL_EVAL_TIMEOUT_SECONDS` | `120` |
| `eval_retries` | `IPL_EVAL_RETRIES` | `1` |
| `eval_dataset_dir` | `IPL_EVAL_DATASET_DIR` | `evals/datasets` |

CLI flags override these settings when provided.
