"""Evaluation run engine.

Orchestrates dataset evaluation with concurrent case execution,
state tracking, JSONL results, and threshold checking.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import click
from pydantic_evals.reporting import EvaluationReport

from finding_extractor.eval.datasets import load_dataset
from finding_extractor.eval.evaluators import (
    AttributeEvaluator,
    FindingDetectionEvaluator,
    LocationEvaluator,
    NonFindingClassificationEvaluator,
    PresenceClassificationEvaluator,
    VerbatimQuoteEvaluator,
)
from finding_extractor.eval.models import EvalInput, EvalRunConfig
from finding_extractor.eval.task import make_eval_task
from finding_extractor.models import ReportExtraction

logger = logging.getLogger(__name__)


def make_run_id() -> str:
    """Generate a timestamped run ID."""
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"eval-{stamp}-{uuid4().hex[:8]}"


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON to file atomically via tmp + rename."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _extract_averages(
    report: EvaluationReport[EvalInput, ReportExtraction, Any],
) -> dict[str, float]:
    """Extract average scores from an EvaluationReport."""
    averages = report.averages()
    if averages is None:
        return {}
    scores: dict[str, float] = {}
    for name, value in averages.scores.items():
        scores[name] = float(value)
    return scores


def _extract_per_case_results(
    report: EvaluationReport[EvalInput, ReportExtraction, Any],
) -> list[dict[str, Any]]:
    """Extract per-case results from an EvaluationReport."""
    results: list[dict[str, Any]] = []
    for case in report.cases:
        case_result: dict[str, Any] = {
            "name": case.name,
            "scores": {k: v.value for k, v in case.scores.items()},
            "assertions": {k: v.value for k, v in case.assertions.items()},
            "task_duration": case.task_duration,
        }
        if case.evaluator_failures:
            case_result["evaluator_failures"] = [str(f) for f in case.evaluator_failures]
        results.append(case_result)
    return results


def _check_thresholds(
    averages: dict[str, float],
    thresholds: dict[str, float],
) -> list[str]:
    """Check if averages meet threshold requirements.

    Returns list of failure messages (empty if all pass).
    """
    failures: list[str] = []
    for metric_name, min_value in thresholds.items():
        actual = averages.get(metric_name)
        if actual is None:
            failures.append(f"Metric {metric_name!r} not found in results")
        elif actual < min_value:
            failures.append(f"Metric {metric_name!r}: {actual:.4f} < threshold {min_value:.4f}")
    return failures


async def run_eval(config: EvalRunConfig) -> tuple[dict[str, float], int]:
    """Run evaluation and return (averages, exit_code).

    Args:
        config: Evaluation run configuration.

    Returns:
        Tuple of (average_scores, exit_code). exit_code is 0 if all
        thresholds pass, 1 if any fail.
    """
    # Set up run directory
    run_dir = Path(config.run_dir) / config.run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # Save run config
    config_path = run_dir / "run_config.json"
    _write_json_atomic(config_path, asdict(config))

    # Load dataset and add evaluators
    dataset = load_dataset(config.dataset_path)
    dataset.evaluators = [
        FindingDetectionEvaluator(),
        PresenceClassificationEvaluator(),
        LocationEvaluator(),
        AttributeEvaluator(),
        VerbatimQuoteEvaluator(),
        NonFindingClassificationEvaluator(),
    ]

    # Create task function
    task_fn = make_eval_task(
        model=config.model,
        reasoning=config.reasoning,
        timeout_seconds=config.timeout_seconds,
    )

    # Run evaluation
    t0 = time.monotonic()
    report = await dataset.evaluate(
        task_fn,
        max_concurrency=config.workers,
        name=f"eval-{config.run_id}",
    )
    elapsed = time.monotonic() - t0

    # Print report
    report.print(include_input=False, include_output=False)

    # Extract and display averages
    averages = _extract_averages(report)

    # Save results
    per_case = _extract_per_case_results(report)
    results_payload = {
        "run_id": config.run_id,
        "model": config.model,
        "reasoning": config.reasoning,
        "dataset": config.dataset_path,
        "duration_seconds": round(elapsed, 2),
        "averages": averages,
        "cases": per_case,
        "thresholds": config.thresholds,
        "completed_at": datetime.now(UTC).isoformat(),
    }
    results_path = run_dir / "results.json"
    _write_json_atomic(results_path, results_payload)

    # Write JSONL per-case results
    jsonl_path = run_dir / "results.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fh:
        for case_data in per_case:
            fh.write(json.dumps(case_data, ensure_ascii=False) + "\n")

    # Check thresholds
    failures = _check_thresholds(averages, config.thresholds)
    if failures:
        click.echo("\nThreshold failures:", err=True)
        for msg in failures:
            click.echo(f"  FAIL: {msg}", err=True)
        return averages, 1

    if config.thresholds:
        click.echo("\nAll thresholds passed.", err=True)

    return averages, 0
