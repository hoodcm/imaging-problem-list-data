"""Reporting utilities for eval run results.

Loads results.json from run directories and formats summaries
and comparisons for CLI output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click

# Consistent metric display order for per-case tables.
# Key metrics are always shown; others shown only when they differ.
METRIC_DISPLAY_ORDER: list[str] = [
    "finding_f1",
    "finding_precision",
    "finding_recall",
    "presence_accuracy",
    "body_region_accuracy",
    "laterality_accuracy",
    "attribute_precision",
    "attribute_recall",
    "verbatim_rate",
    "nonfinding_category_accuracy",
    # Assertions (rendered as PASS/FAIL)
    "verbatim_pass",
]

# Metrics always shown in per-case comparison even when unchanged.
_KEY_METRICS = {"finding_f1", "presence_accuracy", "verbatim_pass"}


def _ordered_metrics(names: set[str]) -> list[str]:
    """Return metric names in canonical display order.

    Metrics listed in METRIC_DISPLAY_ORDER come first (preserving that order),
    followed by any remaining metrics sorted alphabetically.
    """
    ordered = [m for m in METRIC_DISPLAY_ORDER if m in names]
    ordered += sorted(names - set(ordered))
    return ordered


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


def _get_all_case_metrics(case_data: dict[str, Any]) -> dict[str, float | bool]:
    """Merge scores and assertions into a single dict for a case."""
    merged: dict[str, float | bool] = {}
    merged.update(case_data.get("scores", {}))
    merged.update(case_data.get("assertions", {}))
    return merged


def _get_all_case_reasons(case_data: dict[str, Any]) -> dict[str, str]:
    """Merge score_reasons and assertion_reasons into a single dict."""
    merged: dict[str, str] = {}
    merged.update(case_data.get("score_reasons", {}))
    merged.update(case_data.get("assertion_reasons", {}))
    return merged


def _format_metric_value(name: str, value: float | bool) -> str:
    """Format a metric value for display."""
    if isinstance(value, bool):
        return "PASS" if value else "FAIL"
    return f"{value:.4f}"


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

    # Per-case multi-metric comparison
    cases_a = {c["name"]: c for c in results_a.get("cases", [])}
    cases_b = {c["name"]: c for c in results_b.get("cases", [])}
    all_case_names = sorted(set(cases_a) | set(cases_b))

    if all_case_names:
        click.echo(f"\nPer-case Scores: {run_a} \u2192 {run_b}")
        click.echo(
            f"{'Case':<25} {'Metric':<25} {'A':>8} {'B':>8} {'Delta':>8} {'':>3}"
        )
        click.echo(
            f"{'-' * 25} {'-' * 25} {'-' * 8} {'-' * 8} {'-' * 8} {'-' * 3}"
        )
        for name in all_case_names:
            ca = cases_a.get(name, {})
            cb = cases_b.get(name, {})
            metrics_a = _get_all_case_metrics(ca)
            metrics_b = _get_all_case_metrics(cb)
            all_metric_names = set(metrics_a) | set(metrics_b)

            # Order metrics: METRIC_DISPLAY_ORDER first, then alphabetical remainder
            ordered = _ordered_metrics(all_metric_names)

            first_metric = True
            for metric in ordered:
                val_a = metrics_a.get(metric)
                val_b = metrics_b.get(metric)

                # Only show key metrics or metrics that changed
                is_key = metric in _KEY_METRICS
                changed = val_a != val_b
                if not is_key and not changed:
                    continue

                a_str = _format_metric_value(metric, val_a) if val_a is not None else "—"
                b_str = _format_metric_value(metric, val_b) if val_b is not None else "—"

                if (
                    val_a is not None
                    and val_b is not None
                    and not isinstance(val_a, bool)
                    and not isinstance(val_b, bool)
                    and isinstance(val_a, (int, float))
                    and isinstance(val_b, (int, float))
                ):
                    delta = val_b - val_a
                    delta_str = f"{delta:+.4f}"
                    arrow = _direction_arrow(delta)
                elif val_a == val_b:
                    delta_str = ""
                    arrow = "="
                else:
                    delta_str = "—"
                    arrow = " "

                case_col = name if first_metric else ""
                click.echo(
                    f"{case_col:<25} {metric:<25} {a_str:>8} {b_str:>8} "
                    f"{delta_str:>8} {arrow:>3}"
                )
                first_metric = False

    click.echo()


def print_case_detail(
    results: dict[str, Any],
    case_name: str,
    compare_results: dict[str, Any] | None = None,
) -> None:
    """Print detailed view for a single case.

    Args:
        results: Primary run results dict.
        case_name: Name of the case to display.
        compare_results: Optional second run results for comparison mode.

    Raises:
        click.ClickException: If the case is not found.
    """
    # Look up case in primary results
    cases = {c["name"]: c for c in results.get("cases", [])}
    case_a = cases.get(case_name)
    if case_a is None:
        available = ", ".join(sorted(cases)) or "(none)"
        raise click.ClickException(
            f"Case {case_name!r} not found. Available: {available}"
        )

    if compare_results is not None:
        _print_case_detail_comparison(results, case_a, compare_results, case_name)
    else:
        _print_case_detail_single(results, case_a)


def _print_case_detail_single(
    results: dict[str, Any], case_data: dict[str, Any]
) -> None:
    """Print single-run case detail."""
    run_id = results.get("run_id", "unknown")
    model = results.get("model", "unknown")
    duration = case_data.get("task_duration", 0)

    click.echo(f"\n{'=' * 60}")
    click.echo(f"Case: {case_data['name']}")
    click.echo(f"Run: {run_id}")
    click.echo(f"Model: {model}  Duration: {duration:.1f}s")
    click.echo(f"{'=' * 60}")

    reasons = _get_all_case_reasons(case_data)

    # Separate scores and assertions
    scores_dict = case_data.get("scores", {})
    assertions_dict = case_data.get("assertions", {})

    # Print scores
    score_names = _ordered_metrics(set(scores_dict))
    if score_names:
        click.echo("\nScores:")
        for name in score_names:
            value = scores_dict[name]
            val_str = _format_metric_value(name, value)
            reason = reasons.get(name)
            reason_str = f"  ({reason})" if reason else ""
            click.echo(f"  {name:<30} {val_str:>8}{reason_str}")

    # Print assertions
    assertion_names = _ordered_metrics(set(assertions_dict))
    if assertion_names:
        click.echo("\nAssertions:")
        for name in assertion_names:
            value = assertions_dict[name]
            val_str = "PASS" if value else "FAIL"
            reason = reasons.get(name)
            reason_str = f"  ({reason})" if reason else ""
            click.echo(f"  {name:<30} {val_str:>8}{reason_str}")

    click.echo()


def _print_case_detail_comparison(
    results_a: dict[str, Any],
    case_a: dict[str, Any],
    results_b: dict[str, Any],
    case_name: str,
) -> None:
    """Print comparison case detail."""
    cases_b = {c["name"]: c for c in results_b.get("cases", [])}
    case_b = cases_b.get(case_name)
    if case_b is None:
        available = ", ".join(sorted(cases_b)) or "(none)"
        raise click.ClickException(
            f"Case {case_name!r} not found in comparison run. Available: {available}"
        )

    run_a = results_a.get("run_id", "Run A")
    run_b = results_b.get("run_id", "Run B")

    click.echo(f"\n{'=' * 60}")
    click.echo(f"Case: {case_name} ({run_a} \u2192 {run_b})")
    click.echo(f"  A: model={results_a.get('model')}")
    click.echo(f"  B: model={results_b.get('model')}")
    click.echo(f"{'=' * 60}")

    reasons_a = _get_all_case_reasons(case_a)
    reasons_b = _get_all_case_reasons(case_b)

    # Separate scores and assertions
    scores_a = case_a.get("scores", {})
    scores_b = case_b.get("scores", {})
    assertions_a = case_a.get("assertions", {})
    assertions_b = case_b.get("assertions", {})

    # Print scores
    score_names = _ordered_metrics(set(scores_a) | set(scores_b))
    if score_names:
        click.echo(
            f"\n{'Scores:':<32} {'A':>8} {'B':>8} {'Delta':>8} {'':>3}"
        )
        for name in score_names:
            val_a = scores_a.get(name)
            val_b = scores_b.get(name)
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
                f"  {name:<30} {a_str:>8} {b_str:>8} {delta_str:>8} {arrow:>3}"
            )
            # Show reasons per-run when they exist and differ
            reason_a = reasons_a.get(name)
            reason_b = reasons_b.get(name)
            if reason_a:
                click.echo(f"    A: {reason_a}")
            if reason_b:
                click.echo(f"    B: {reason_b}")

    # Print assertions
    assertion_names = _ordered_metrics(set(assertions_a) | set(assertions_b))
    if assertion_names:
        click.echo(
            f"\n{'Assertions:':<32} {'A':>8} {'B':>8} {'Delta':>8} {'':>3}"
        )
        for name in assertion_names:
            val_a = assertions_a.get(name)
            val_b = assertions_b.get(name)
            a_str = ("PASS" if val_a else "FAIL") if val_a is not None else "—"
            b_str = ("PASS" if val_b else "FAIL") if val_b is not None else "—"
            if val_a == val_b:
                delta_str = ""
                arrow = "="
            else:
                delta_str = "—"
                arrow = " "
            click.echo(
                f"  {name:<30} {a_str:>8} {b_str:>8} {delta_str:>8} {arrow:>3}"
            )
            reason_a = reasons_a.get(name)
            reason_b = reasons_b.get(name)
            if reason_a:
                click.echo(f"    A: {reason_a}")
            if reason_b:
                click.echo(f"    B: {reason_b}")

    click.echo()
