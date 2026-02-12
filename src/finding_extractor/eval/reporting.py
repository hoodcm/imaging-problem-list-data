"""Reporting utilities for eval run results.

Loads results.json from run directories and formats summaries
and comparisons for CLI output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click


def load_run_results(run_dir: Path, run_id: str) -> dict[str, Any]:
    """Load results.json from a run directory.

    Args:
        run_dir: Base directory for all runs.
        run_id: Specific run identifier.

    Returns:
        Parsed results dict.

    Raises:
        click.ClickException: If the run or results file is not found.
    """
    results_path = run_dir / run_id / "results.json"
    if not results_path.exists():
        raise click.ClickException(f"Run not found: {results_path}")
    return json.loads(results_path.read_text(encoding="utf-8"))


def find_latest_run(run_dir: Path) -> str | None:
    """Find the most recent run by directory modification time.

    Returns:
        Run ID string, or None if no runs exist.
    """
    if not run_dir.exists():
        return None

    candidates = [
        d for d in run_dir.iterdir() if d.is_dir() and (d / "results.json").exists()
    ]
    if not candidates:
        return None

    # Sort by mtime descending, return the most recent
    candidates.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return candidates[0].name


def print_run_summary(results: dict[str, Any]) -> None:
    """Print a formatted summary of a single eval run."""
    run_id = results.get("run_id", "unknown")
    model = results.get("model", "unknown")
    dataset = results.get("dataset", "unknown")
    duration = results.get("duration_seconds", 0)
    completed = results.get("completed_at", "")

    click.echo(f"\n{'=' * 60}")
    click.echo(f"Run: {run_id}")
    click.echo(f"Model: {model}  Dataset: {dataset}")
    click.echo(f"Duration: {duration}s  Completed: {completed}")
    click.echo(f"{'=' * 60}")

    # Averages table
    averages = results.get("averages", {})
    if averages:
        click.echo(f"\n{'Metric':<35} {'Score':>10}")
        click.echo(f"{'-' * 35} {'-' * 10}")
        for metric, value in sorted(averages.items()):
            click.echo(f"{metric:<35} {value:>10.4f}")

    # Per-case breakdown
    cases = results.get("cases", [])
    if cases:
        click.echo(f"\n{'Case':<30} {'F1':>8} {'Presence':>10} {'Verbatim':>10}")
        click.echo(f"{'-' * 30} {'-' * 8} {'-' * 10} {'-' * 10}")
        for case in cases:
            name = case.get("name", "?")
            scores = case.get("scores", {})
            assertions = case.get("assertions", {})
            f1 = scores.get("finding_f1", "—")
            presence = scores.get("presence_accuracy", "—")
            verbatim = assertions.get("verbatim_pass", scores.get("verbatim_pass", "—"))
            f1_str = f"{f1:.4f}" if isinstance(f1, (int, float)) else str(f1)
            pres_str = f"{presence:.4f}" if isinstance(presence, (int, float)) else str(presence)
            verb_str = str(verbatim) if isinstance(verbatim, bool) else (
                f"{verbatim:.4f}" if isinstance(verbatim, (int, float)) else str(verbatim)
            )
            click.echo(f"{name:<30} {f1_str:>8} {pres_str:>10} {verb_str:>10}")

    # Thresholds
    thresholds = results.get("thresholds", {})
    if thresholds:
        click.echo(f"\nThresholds: {thresholds}")

    click.echo()


def _direction_arrow(delta: float) -> str:
    """Return a colored arrow for positive/negative/zero delta."""
    if delta > 0.001:
        return click.style("\u2191", fg="green")  # ↑
    elif delta < -0.001:
        return click.style("\u2193", fg="red")  # ↓
    else:
        return "="


def print_comparison(results_a: dict[str, Any], results_b: dict[str, Any]) -> None:
    """Print side-by-side comparison of two eval runs."""
    run_a = results_a.get("run_id", "Run A")
    run_b = results_b.get("run_id", "Run B")

    click.echo(f"\n{'=' * 70}")
    click.echo(f"Comparison: {run_a} vs {run_b}")
    click.echo(f"  A: model={results_a.get('model')}  dataset={results_a.get('dataset')}")
    click.echo(f"  B: model={results_b.get('model')}  dataset={results_b.get('dataset')}")
    click.echo(f"{'=' * 70}")

    # Averages comparison
    avgs_a = results_a.get("averages", {})
    avgs_b = results_b.get("averages", {})
    all_metrics = sorted(set(avgs_a) | set(avgs_b))

    if all_metrics:
        click.echo(
            f"\n{'Metric':<30} {'A':>10} {'B':>10} {'Delta':>10} {'':>3}"
        )
        click.echo(f"{'-' * 30} {'-' * 10} {'-' * 10} {'-' * 10} {'-' * 3}")
        for metric in all_metrics:
            val_a = avgs_a.get(metric)
            val_b = avgs_b.get(metric)
            a_str = f"{val_a:.4f}" if val_a is not None else "—"
            b_str = f"{val_b:.4f}" if val_b is not None else "—"
            if val_a is not None and val_b is not None:
                delta = val_b - val_a
                delta_str = f"{delta:+.4f}"
                arrow = _direction_arrow(delta)
            else:
                delta_str = "—"
                arrow = " "
            click.echo(
                f"{metric:<30} {a_str:>10} {b_str:>10} {delta_str:>10} {arrow:>3}"
            )

    # Per-case comparison
    cases_a = {c["name"]: c for c in results_a.get("cases", [])}
    cases_b = {c["name"]: c for c in results_b.get("cases", [])}
    all_case_names = sorted(set(cases_a) | set(cases_b))

    if all_case_names:
        click.echo(f"\nPer-case F1: {run_a} → {run_b}")
        click.echo(f"{'Case':<30} {'A':>8} {'B':>8} {'Delta':>8} {'':>3}")
        click.echo(f"{'-' * 30} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 3}")
        for name in all_case_names:
            ca = cases_a.get(name, {})
            cb = cases_b.get(name, {})
            f1_a = ca.get("scores", {}).get("finding_f1")
            f1_b = cb.get("scores", {}).get("finding_f1")
            a_str = f"{f1_a:.4f}" if f1_a is not None else "—"
            b_str = f"{f1_b:.4f}" if f1_b is not None else "—"
            if f1_a is not None and f1_b is not None:
                delta = f1_b - f1_a
                delta_str = f"{delta:+.4f}"
                arrow = _direction_arrow(delta)
            else:
                delta_str = "—"
                arrow = " "
            click.echo(f"{name:<30} {a_str:>8} {b_str:>8} {delta_str:>8} {arrow:>3}")

    click.echo()
