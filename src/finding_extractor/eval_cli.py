"""CLI for the evaluation harness.

Usage:
    finding-extractor-eval run --dataset smoke --model openai:gpt-5-mini
    finding-extractor-eval import-baseline sample_data/example2 --dataset comprehensive --glob "*.md"
    finding-extractor-eval report [RUN_ID] [--compare OTHER_RUN_ID]
"""

from __future__ import annotations

from pathlib import Path

import click
from asyncer import runnify
from pydantic_evals import Dataset

from finding_extractor.config import get_settings
from finding_extractor.eval.datasets import import_baseline_cases, load_dataset, save_dataset
from finding_extractor.eval.models import EvalInput, EvalMetadata, EvalRunConfig
from finding_extractor.eval.reporting import (
    display_case_detail,
    display_comparison,
    display_report,
    find_latest_run,
    load_report,
    load_run_results,
    print_legacy_summary,
)
from finding_extractor.eval.runner import make_run_id, run_eval
from finding_extractor.logging_setup import setup_logging
from finding_extractor.model_policy import validate_model_id
from finding_extractor.models import ReportExtraction
from finding_extractor.observability import configure_logfire
from finding_extractor.providers import resolve_effective_reasoning
from finding_extractor.runtime_budget import (
    DEFAULT_MAX_PREDICTED_RUNTIME_SECONDS,
    build_runtime_preflight,
)

_run_eval_sync = runnify(run_eval)


@click.group(name="finding-extractor-eval")
def cli() -> None:
    """Evaluation harness for extraction quality measurement."""


@cli.command("run")
@click.option(
    "--dataset",
    default="smoke",
    show_default=True,
    help="Dataset name (resolved from eval_dataset_dir) or path to YAML file.",
)
@click.option(
    "--model",
    default=None,
    help="Model id override (default: from settings).",
)
@click.option(
    "--reasoning",
    type=click.Choice(["none", "minimal", "low", "medium", "high"], case_sensitive=False),
    default=None,
    help="Reasoning level override.",
)
@click.option(
    "--workers",
    type=click.IntRange(min=1, max=16),
    default=None,
    help="Concurrent case workers.",
)
@click.option(
    "--timeout-seconds",
    type=click.IntRange(min=10),
    default=None,
    help="Per-case timeout in seconds.",
)
@click.option(
    "--run-id",
    default=None,
    help="Optional run id (defaults to generated id).",
)
@click.option(
    "--run-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory for run state files.",
)
@click.option(
    "--threshold-f1",
    type=float,
    default=None,
    help="Minimum finding_f1 score (exit non-zero if below).",
)
@click.option(
    "--threshold-presence",
    type=float,
    default=None,
    help="Minimum presence_accuracy score (exit non-zero if below).",
)
@click.option(
    "--threshold-verbatim",
    is_flag=True,
    default=False,
    help="Require all verbatim checks to pass (verbatim_pass >= 1.0).",
)
@click.option(
    "--retries",
    type=click.IntRange(min=0, max=5),
    default=None,
    help="Per-case retries on transient failure (0–5, default: from settings).",
)
@click.option(
    "--max-predicted-runtime-seconds",
    type=click.IntRange(min=60),
    default=None,
    help=(
        "Fail fast if conservative runtime bound exceeds this value "
        "(default: 900 seconds)."
    ),
)
@click.option(
    "--allow-slow",
    is_flag=True,
    default=False,
    help="Override runtime guard and run even when the predicted bound is high.",
)
def run_command(
    dataset: str,
    model: str | None,
    reasoning: str | None,
    workers: int | None,
    timeout_seconds: int | None,
    run_id: str | None,
    run_dir: Path | None,
    threshold_f1: float | None,
    threshold_presence: float | None,
    threshold_verbatim: bool,
    retries: int | None,
    max_predicted_runtime_seconds: int | None,
    allow_slow: bool,
) -> None:
    """Run evaluation on a dataset."""
    settings = get_settings()
    logfire_enabled = configure_logfire(runtime="cli")
    setup_logging(settings, include_logfire_processor=logfire_enabled)

    # Resolve settings
    resolved_model = model or settings.default_model
    validate_model_id(resolved_model)
    effective_reasoning = resolve_effective_reasoning(resolved_model, reasoning)

    resolved_workers = workers if workers is not None else settings.eval_workers
    resolved_timeout = (
        timeout_seconds if timeout_seconds is not None else settings.eval_timeout_seconds
    )
    resolved_run_dir = (run_dir or settings.eval_run_dir).resolve()
    resolved_run_id = run_id or make_run_id()
    resolved_retries = retries if retries is not None else settings.eval_retries
    resolved_max_predicted_runtime = (
        max_predicted_runtime_seconds
        if max_predicted_runtime_seconds is not None
        else DEFAULT_MAX_PREDICTED_RUNTIME_SECONDS
    )

    eval_dataset = load_dataset(dataset)
    case_count = len(eval_dataset.cases)
    preflight_line, preflight_error, preflight_warning = build_runtime_preflight(
        command_label="EVAL",
        item_label="cases",
        item_count=case_count,
        workers=resolved_workers,
        timeout_seconds=resolved_timeout,
        retries=resolved_retries,
        budget_seconds=resolved_max_predicted_runtime,
        allow_slow=allow_slow,
    )
    click.echo(preflight_line)
    if preflight_error:
        raise click.ClickException(preflight_error)
    if preflight_warning:
        click.echo(preflight_warning, err=True)

    # Build thresholds
    thresholds: dict[str, float] = {}
    if threshold_f1 is not None:
        thresholds["finding_f1"] = threshold_f1
    if threshold_presence is not None:
        thresholds["presence_accuracy"] = threshold_presence
    if threshold_verbatim:
        thresholds["verbatim_pass"] = 1.0

    config = EvalRunConfig(
        run_id=resolved_run_id,
        dataset_path=dataset,
        model=resolved_model,
        reasoning=effective_reasoning,
        workers=resolved_workers,
        timeout_seconds=resolved_timeout,
        run_dir=str(resolved_run_dir),
        retries=resolved_retries,
        thresholds=thresholds,
    )

    click.echo(
        f"EVAL run_id={config.run_id} dataset={config.dataset_path} "
        f"model={config.model} reasoning={config.reasoning or 'default'} "
        f"workers={config.workers} retries={config.retries} cases={case_count}"
    )

    _averages, exit_code = _run_eval_sync(config=config)

    if exit_code:
        raise SystemExit(exit_code)


@cli.command("import-baseline")
@click.argument("source_dir", type=click.Path(exists=True, file_okay=False, path_type=Path))
@click.option(
    "--dataset",
    required=True,
    help="Target dataset name (e.g., 'comprehensive') or path to YAML file.",
)
@click.option("--glob", "file_glob", default="*.txt", show_default=True, help="Glob pattern for report files.")
@click.option(
    "--output-suffix",
    default=".extracted.json",
    show_default=True,
    help="Suffix convention for extraction files.",
)
@click.option(
    "--append/--no-append",
    default=True,
    show_default=True,
    help="Append to existing dataset or overwrite.",
)
@click.option(
    "--source-label",
    default=None,
    help="Label for source_file metadata (default: directory basename).",
)
@click.option(
    "--model-filter",
    default=None,
    help="Only import extractions from a specific model.",
)
def import_baseline_command(
    source_dir: Path,
    dataset: str,
    file_glob: str,
    output_suffix: str,
    append: bool,
    source_label: str | None,
    model_filter: str | None,
) -> None:
    """Import reviewed batch extraction results as ground truth eval cases."""
    new_cases = import_baseline_cases(
        source_dir,
        glob=file_glob,
        output_suffix=output_suffix,
        source_label=source_label,
        model_filter=model_filter,
    )

    if not new_cases:
        raise click.ClickException("No cases imported. Check source directory and file patterns.")

    # Load existing dataset if appending
    existing_cases: list = []
    if append:
        try:
            existing = load_dataset(dataset)
            existing_cases = list(existing.cases)
            click.echo(f"Appending to existing dataset ({len(existing_cases)} cases).")
        except FileNotFoundError:
            pass  # No existing dataset, start fresh

    # Deduplicate: new cases override existing ones with the same name
    new_names = {c.name for c in new_cases}
    merged_cases = [c for c in existing_cases if c.name not in new_names] + new_cases
    result_dataset = Dataset[EvalInput, ReportExtraction, EvalMetadata](cases=merged_cases)
    output_path = save_dataset(result_dataset, dataset)

    click.echo(
        f"Imported {len(new_cases)} cases "
        f"(total: {len(merged_cases)}) → {output_path}"
    )


@cli.command("report")
@click.argument("run_id", required=False, default=None)
@click.option(
    "--compare",
    "compare_run_id",
    default=None,
    help="Second run ID for side-by-side comparison.",
)
@click.option(
    "--case",
    "case_name",
    default=None,
    help="Show detailed view for a specific case.",
)
@click.option(
    "--run-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory containing run results.",
)
def report_command(
    run_id: str | None,
    compare_run_id: str | None,
    case_name: str | None,
    run_dir: Path | None,
) -> None:
    """View results from a previous eval run, optionally comparing two runs."""
    settings = get_settings()
    resolved_run_dir = (run_dir or settings.eval_run_dir).resolve()

    # Resolve run ID
    if run_id is None:
        run_id = find_latest_run(resolved_run_dir)
        if run_id is None:
            raise click.ClickException(
                f"No runs found in {resolved_run_dir}. Run an eval first."
            )
        click.echo(f"Latest run: {run_id}")

    report = load_report(resolved_run_dir, run_id)

    if report is not None:
        compare_report = None
        if compare_run_id:
            compare_report = load_report(resolved_run_dir, compare_run_id)
            if compare_report is None:
                raise click.ClickException(
                    f"Run {compare_run_id!r} has no report.json. "
                    "Both runs need report.json for comparison."
                )

        if case_name:
            display_case_detail(report, case_name, compare_report)
        elif compare_report is not None:
            display_comparison(report, compare_report)
        else:
            display_report(report)
    else:
        # Legacy fallback (no report.json)
        if compare_run_id or case_name:
            raise click.ClickException(
                f"Run {run_id!r} uses legacy format. "
                "Re-run eval to generate report.json for comparison/detail."
            )
        results = load_run_results(resolved_run_dir, run_id)
        print_legacy_summary(results)


if __name__ == "__main__":
    cli()
