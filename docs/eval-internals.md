# Evaluation Harness — Developer Guide

## Architecture

```
finding-extractor-eval run --dataset smoke
         │
         ▼
    eval_cli.py          CLI entry point (Click)
         │
         ▼
    eval/runner.py       Run engine (load dataset, run, persist, check thresholds)
         │
    ┌────┼────────────────────────┐
    │    ▼                        │
    │  eval/datasets.py           │  Dataset loading (YAML → pydantic-evals Dataset)
    │    │                        │
    │    ▼                        │
    │  eval/evaluators.py         │  6 custom Evaluator subclasses
    │    │                        │
    │    ▼                        │
    │  eval/matching.py           │  Jaccard-based finding matcher
    │    │                        │
    │    ▼                        │
    │  eval/task.py               │  Task adapter (EvalInput → ReportExtraction)
    │    │                        │
    │    ▼                        │
    │  agent.extract_findings()   │  Actual extraction via PydanticAI
    └─────────────────────────────┘
```

## Module Map

| Module | Purpose |
|--------|---------|
| `eval/__init__.py` | Re-exports public names |
| `eval/models.py` | `EvalInput`, `EvalMetadata`, `EvalRunConfig` |
| `eval/matching.py` | Greedy best-match finding alignment |
| `eval/evaluators.py` | 6 scoring evaluators |
| `eval/task.py` | `make_eval_task()` — wraps `extract_findings()` for pydantic-evals |
| `eval/datasets.py` | `load_dataset()`, `build_smoke_dataset()` |
| `eval/runner.py` | `run_eval()` — orchestrates load → evaluate → persist → threshold check |
| `eval_cli.py` | Click CLI entry point |

## Finding Matching Algorithm (`matching.py`)

The matching algorithm aligns expected findings (ground truth) to actual findings (extractor output) before evaluators score individual dimensions.

### Steps

1. **Tokenize** each finding: lowercase-split `finding_name` + `report_text` → `set[str]`.
2. **Compute pairwise Jaccard similarity** between all expected × actual token sets.
3. **Apply presence bonus** (+0.1) when `expected.presence == actual.presence`. This favors matching findings with the same classification.
4. **Greedy best-match**: sort all pairs by similarity descending, greedily assign pairs (each finding matched at most once).
5. **Threshold filter**: only pairs with similarity ≥ threshold (default 0.3) are considered.

### Output

`MatchResult` contains:
- `matches` — aligned `(expected, actual, similarity)` triples
- `unmatched_expected` — false negatives (ground truth not matched)
- `unmatched_actual` — false positives (extractor output not matched)

### Design Decisions

- **No external NLP dependencies**: tokenization is simple whitespace split, keeping the eval fast and deterministic.
- **0.3 threshold**: tuned to allow fuzzy matches (e.g., "renal calculus" vs "renal stone") while rejecting unrelated findings.
- **Presence bonus**: prevents matching a "present" finding against an "absent" finding with the same name when a better option exists.

## Evaluator Design (`evaluators.py`)

All evaluators are `@dataclass` classes inheriting from `pydantic_evals.evaluators.Evaluator[EvalInput, ReportExtraction]`. They implement `evaluate(ctx) -> dict[str, ...]` returning scores (float), assertions (bool), or `EvaluationReason` (value + diagnostic reason).

### Evaluator Summary

| Evaluator | Metrics | Notes |
|-----------|---------|-------|
| `FindingDetectionEvaluator` | `finding_precision`, `finding_recall`, `finding_f1` | `finding_f1` returns `EvaluationReason` with match/FP/FN counts. |
| `PresenceClassificationEvaluator` | `presence_accuracy` | Only scores matched findings. |
| `LocationEvaluator` | `body_region_accuracy`, `laterality_accuracy` | Laterality only evaluated when expected has laterality. |
| `AttributeEvaluator` | `attribute_precision`, `attribute_recall` | Attribute keys compared (not values). |
| `VerbatimQuoteEvaluator` | `verbatim_pass` (bool assertion), `verbatim_rate` (float score) | `verbatim_pass` is a bool → routes to `case.assertions`. Returns `EvaluationReason` with verbatim counts. |
| `NonFindingClassificationEvaluator` | `nonfinding_category_accuracy` | Uses `tokenize()`/`jaccard_similarity()` from `matching.py`. |

### Shared Utilities

- **`tokenize()` / `jaccard_similarity()`**: Public functions in `matching.py`, reused by `NonFindingClassificationEvaluator` for non-finding text matching (replaces inline Jaccard calculation).

### Inline Pattern

All four finding-based evaluators (`FindingDetection`, `PresenceClassification`, `Location`, `Attribute`) follow a consistent inline pattern:
1. Read `ctx.expected_output` and `ctx.output`
2. Return default zeros if expected is `None`
3. Call `match_findings(expected.findings, actual.findings, threshold=self.threshold)`
4. Score the dimension from the match result

This pattern was kept inline rather than extracted into a shared helper because the per-evaluator default dicts differ, the inline code is clear and type-safe, and the duplication is minimal (3 lines per evaluator).

### Bool Assertions vs Float Scores

pydantic-evals routes evaluator return values by type:
- **`bool`** values → `case.assertions` (pass/fail semantics, shown as checkmarks in reports)
- **`float`/`int`** values → `case.scores` (continuous metrics, averaged in reports)
- **`EvaluationReason`** wraps either type with a diagnostic `reason` string

`verbatim_pass` returns `bool` via `EvaluationReason(value=True/False, reason=...)`, so it appears in assertions. `verbatim_rate` stays as a float score.

The runner's `_extract_averages()` computes per-assertion pass rates from per-case data and merges them into the averages dict alongside scores, so threshold checking works uniformly for both.

### Edge Case Handling

- **No expected output**: all evaluators return 0.0 (except VerbatimQuoteEvaluator, which doesn't need expected output).
- **Both empty**: detection returns 1.0 (nothing to detect, nothing missed). Presence and non-finding return 1.0.
- **No matches but expected non-empty**: presence returns 0.0 (all missed).

## Dataset Format

Datasets are YAML files using the pydantic-evals `Dataset.to_file()` format:

```yaml
cases:
- name: ct_abdomen_pelvis
  inputs:
    report_text: "History: flank pain..."
    exam_description: null
  metadata:
    source_file: examples.py
    modality: CT
    body_region: abdomen
  expected_output:
    exam_info:
      study_description: CT Abdomen and Pelvis WO contrast
    findings:
    - finding_name: renal calculus
      presence: present
      location:
        body_region: abdomen
        specific_anatomy: right lower pole
        laterality: right
      attributes:
      - key: size
        value: 3 mm
      report_text: "Stable bilateral renal stones..."
    non_finding_text:
    - text: "History: flank pain, h/o stones"
      category: clinical_history
  evaluators: []
evaluators: []
```

Key points:
- `expected_output` uses the native `ReportExtraction` format (same as extraction output).
- `metadata` fields are optional; used for filtering and reporting.
- Per-case `evaluators` can override the dataset-level evaluators (empty = use dataset defaults).

## Runner Architecture (`runner.py`)

The run engine follows the pattern from `batch_cli.py`:

1. **Load dataset** via `load_dataset()`.
2. **Attach evaluators** (all 6) to the dataset.
3. **Create task function** via `make_eval_task(model, reasoning, timeout)`.
4. **Build retry config** via `_build_retry_config(retries)` — returns a `RetryConfig` (tenacity `stop_after_attempt` + `wait_exponential`) or `None` when retries=0.
5. **Execute** via `dataset.evaluate(task_fn, max_concurrency=workers, retry_task=retry_task)`.
6. **Extract averages** — `_extract_averages()` reads `report.averages().scores` for float metrics and computes per-assertion pass rates from per-case `case.assertions` data (since `report.averages().assertions` is a single aggregate float, not a per-metric dict).
7. **Persist results** to `{run_dir}/{run_id}/`:
   - `run_config.json` — frozen configuration (includes `retries`)
   - `results.json` — averages + per-case scores + metadata
   - `results.jsonl` — one line per case
8. **Check thresholds** and return exit code.

Concurrency is handled by pydantic-evals' built-in `max_concurrency` parameter (no custom worker pool needed). Retries use pydantic-evals' native `retry_task` parameter backed by tenacity.

## CLI Architecture (`eval_cli.py`)

- Click group with `run` subcommand.
- Uses `asyncer.runnify()` to bridge the async `run_eval()` to synchronous Click.
- Calls `configure_logfire(runtime="cli")` + `setup_logging()` at startup — same pattern as all other CLI entry points.
- Runner uses `structlog.get_logger()` for structured logging output.
- Settings resolution: CLI flags > config settings > defaults.
- Model and reasoning validation happens before the run starts.
- Threshold flags are optional; when set, the CLI exits non-zero if any threshold fails.

## Test Coverage

| Test File | Coverage |
|-----------|----------|
| `tests/test_eval_matching.py` | Tokenization, Jaccard similarity, match_findings edge cases, integration with examples |
| `tests/test_eval_evaluators.py` | All 6 evaluators with mock context, integration with CT abdomen example |
| `tests/test_eval_cli.py` | CLI help, run with mocked runner, threshold logic, dataset loading |

Tests use a `FakeEvaluatorContext` dataclass that stands in for pydantic-evals' `EvaluatorContext`, allowing unit testing of evaluator logic without running the full framework.

## Adding a New Evaluator

1. Create a `@dataclass` class in `evaluators.py` inheriting from `Evaluator[EvalInput, ReportExtraction]`.
2. Implement `evaluate(ctx) -> dict[str, float]` returning named metrics.
3. Add the evaluator to the list in `runner.py:run_eval()`.
4. Add tests in `test_eval_evaluators.py`.
5. If threshold support is needed, add a CLI flag in `eval_cli.py` and wire it into the thresholds dict.

## Adding a New Dataset

1. Create a YAML file in `evals/datasets/` following the format above.
2. Run it: `finding-extractor-eval run --dataset your_dataset_name`
3. Or build programmatically using pydantic-evals' `Dataset` API:

```python
from pydantic_evals import Case, Dataset
from finding_extractor.eval.models import EvalInput, EvalMetadata
from finding_extractor.models import ReportExtraction

dataset = Dataset(cases=[
    Case(
        name="my_case",
        inputs=EvalInput(report_text="..."),
        expected_output=ReportExtraction(...),
        metadata=EvalMetadata(modality="CT", body_region="chest"),
    ),
])
dataset.to_file("evals/datasets/my_dataset.yaml")
```
