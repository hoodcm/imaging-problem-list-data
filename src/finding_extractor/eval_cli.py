"""CLI for the evaluation harness.

Usage:
    finding-extractor-eval run --dataset smoke --model openai:gpt-5-mini
"""

from __future__ import annotations

from pathlib import Path

import click
from asyncer import runnify

from finding_extractor.agent import validate_reasoning_for_model
from finding_extractor.config import get_settings
from finding_extractor.eval.models import EvalRunConfig
from finding_extractor.eval.runner import make_run_id, run_eval
from finding_extractor.logging_setup import setup_logging
from finding_extractor.model_policy import validate_model_id
from finding_extractor.observability import configure_logfire

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
) -> None:
    """Run evaluation on a dataset."""
    settings = get_settings()
    logfire_enabled = configure_logfire(runtime="cli")
    setup_logging(settings, include_logfire_processor=logfire_enabled)

    # Resolve settings
    resolved_model = model or settings.default_model
    validate_model_id(resolved_model)
    if reasoning is not None:
        validate_reasoning_for_model(resolved_model, reasoning)

    resolved_workers = workers if workers is not None else settings.eval_workers
    resolved_timeout = (
        timeout_seconds if timeout_seconds is not None else settings.eval_timeout_seconds
    )
    resolved_run_dir = (run_dir or settings.eval_run_dir).resolve()
    resolved_run_id = run_id or make_run_id()
    resolved_retries = retries if retries is not None else settings.eval_retries

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
        reasoning=reasoning,
        workers=resolved_workers,
        timeout_seconds=resolved_timeout,
        run_dir=str(resolved_run_dir),
        retries=resolved_retries,
        thresholds=thresholds,
    )

    click.echo(
        f"EVAL run_id={config.run_id} dataset={config.dataset_path} "
        f"model={config.model} reasoning={config.reasoning or 'default'} "
        f"workers={config.workers} retries={config.retries}"
    )

    _averages, exit_code = _run_eval_sync(config=config)

    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    cli()
