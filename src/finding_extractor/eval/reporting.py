"""Reporting utilities for eval run results.

Loads results.json / report.json from run directories and formats
summaries and comparisons for CLI output using pydantic-evals native
Rich reporting.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from pydantic_evals.reporting import EvaluationReport, EvaluationReportAdapter


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
        d
        for d in run_dir.iterdir()
        if d.is_dir() and ((d / "report.json").exists() or (d / "results.json").exists())
    ]
    if not candidates:
        return None

    # Sort by mtime descending, return the most recent
    candidates.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    return candidates[0].name


# ---------------------------------------------------------------------------
# Native pydantic-evals report loading and display
# ---------------------------------------------------------------------------


def load_report(run_dir: Path, run_id: str) -> EvaluationReport | None:
    """Load report.json from a run directory.

    Returns None if the file doesn't exist (legacy runs that predate
    report.json persistence).
    """
    report_path = run_dir / run_id / "report.json"
    if not report_path.exists():
        return None
    data = json.loads(report_path.read_text(encoding="utf-8"))
    return EvaluationReportAdapter.validate_python(data)


def display_report(report: EvaluationReport) -> None:
    """Display a single run using pydantic-evals native Rich output."""
    report.print(include_input=False, include_output=False, include_reasons=True)


def display_comparison(
    primary: EvaluationReport,
    compare: EvaluationReport,
) -> None:
    """Display diff showing change from primary to compare.

    pydantic-evals' ``self.print(baseline=other)`` renders "other → self"
    with deltas = self - other, so we call compare.print(baseline=primary)
    to get "primary → compare" with positive deltas meaning compare improved.
    """
    compare.print(
        baseline=primary,
        include_input=False,
        include_output=False,
        include_reasons=True,
    )


def display_case_detail(
    primary: EvaluationReport,
    case_name: str,
    compare: EvaluationReport | None = None,
) -> None:
    """Display detail for a single case, with optional comparison.

    Filters the report(s) to the matching case and prints. When compare
    is provided, shows diff from primary to compare (same direction as
    ``display_comparison``).

    Raises:
        click.ClickException: If the case is not found.
    """
    matching = [c for c in primary.cases if c.name == case_name]
    if not matching:
        available = ", ".join(sorted(c.name for c in primary.cases)) or "(none)"
        raise click.ClickException(f"Case {case_name!r} not found. Available: {available}")

    filtered_primary = EvaluationReport(
        name=primary.name,
        cases=matching,
        experiment_metadata=primary.experiment_metadata,
    )

    if compare is not None:
        compare_matching = [c for c in compare.cases if c.name == case_name]
        if not compare_matching:
            available = (
                ", ".join(sorted(c.name for c in compare.cases)) or "(none)"
            )
            raise click.ClickException(
                f"Case {case_name!r} not found in comparison run. Available: {available}"
            )
        filtered_compare = EvaluationReport(
            name=compare.name,
            cases=compare_matching,
            experiment_metadata=compare.experiment_metadata,
        )
        filtered_compare.print(
            baseline=filtered_primary,
            include_input=False,
            include_output=False,
            include_reasons=True,
        )
    else:
        filtered_primary.print(
            include_input=False,
            include_output=False,
            include_reasons=True,
        )


# ---------------------------------------------------------------------------
# Legacy fallback (runs without report.json)
# ---------------------------------------------------------------------------


def print_legacy_summary(results: dict[str, Any]) -> None:
    """Minimal display for old runs without report.json.

    Shows averages table and case names with a note to re-run for
    full Rich reporting.
    """
    run_id = results.get("run_id", "unknown")
    model = results.get("model", "unknown")
    dataset = results.get("dataset", "unknown")
    duration = results.get("duration_seconds", 0)

    click.echo(f"\nLegacy run: {run_id}")
    click.echo(f"Model: {model}  Dataset: {dataset}  Duration: {duration}s")

    averages = results.get("averages", {})
    if averages:
        click.echo(f"\n{'Metric':<35} {'Score':>10}")
        click.echo(f"{'-' * 35} {'-' * 10}")
        for metric, value in sorted(averages.items()):
            click.echo(f"{metric:<35} {value:>10.4f}")

    cases = results.get("cases", [])
    if cases:
        case_names = [c.get("name", "?") for c in cases]
        click.echo(f"\nCases: {', '.join(case_names)}")

    click.echo(
        "\nNote: This run uses legacy format. Re-run the eval to generate "
        "report.json for Rich display, comparison, and per-case detail."
    )
