"""Batch extraction CLI with local in-process workers.

V1 scope:
- local execution only (no broker/TaskIQ path)
- interactive and detached run modes
- status visibility from local run-state files
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

import click
from asyncer import runnify

from finding_extractor.config import get_settings
from finding_extractor.extraction_runtime import run_extraction_runtime
from finding_extractor.logging_setup import setup_logging
from finding_extractor.model_policy import validate_model_id
from finding_extractor.observability import configure_logfire
from finding_extractor.providers import resolve_runtime_reasoning
from finding_extractor.runtime_budget import (
    DEFAULT_MAX_PREDICTED_RUNTIME_SECONDS,
    build_runtime_preflight,
)
from finding_extractor.store import ExtractionStore

RunMode = Literal["interactive", "detached"]
_RUN_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TERMINAL_STATUSES = {"completed", "completed_with_errors", "failed"}


@dataclass(frozen=True)
class BatchRunConfig:
    run_id: str
    mode: RunMode
    inputs: list[str]
    output_dir: str | None
    suffix: str
    model: str
    reasoning: str | None
    exam_type: str | None
    workers: int
    timeout_seconds: int
    retries: int
    validate: bool
    resume: bool
    store: bool
    db_path: str
    status_interval_seconds: float
    manifest_path: str | None
    run_dir: str


@dataclass(frozen=True)
class RunPaths:
    base_dir: Path
    state_path: Path
    results_path: Path
    log_path: Path
    pid_path: Path
    config_path: Path


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _now_epoch() -> float:
    return time.time()


def _make_run_id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"{stamp}-{uuid4().hex[:8]}"


def _collect_input_files(
    inputs: tuple[Path, ...], glob_pattern: str, recursive: bool
) -> list[Path]:
    files: list[Path] = []
    for input_path in inputs:
        if input_path.is_file():
            files.append(input_path.resolve())
            continue
        iterator = input_path.rglob(glob_pattern) if recursive else input_path.glob(glob_pattern)
        files.extend(path.resolve() for path in iterator if path.is_file())
    return sorted(set(files))


def _resolve_output_path(source_path: Path, output_dir: Path | None, suffix: str) -> Path:
    if output_dir is None:
        return source_path.with_suffix(suffix)
    return output_dir / f"{source_path.stem}{suffix}"


def _validate_output_collisions(files: list[Path], output_dir: Path | None, suffix: str) -> None:
    seen: dict[Path, Path] = {}
    for source_path in files:
        out = _resolve_output_path(source_path, output_dir, suffix)
        existing = seen.get(out)
        if existing is not None and existing != source_path:
            raise click.ClickException(
                "Output collision detected. Use a different --output-dir or rename inputs. "
                f"Both '{existing}' and '{source_path}' map to '{out}'."
            )
        seen[out] = source_path


def _run_paths(run_dir: Path, run_id: str) -> RunPaths:
    base_dir = run_dir / run_id
    return RunPaths(
        base_dir=base_dir,
        state_path=base_dir / "state.json",
        results_path=base_dir / "results.jsonl",
        log_path=base_dir / "log.txt",
        pid_path=base_dir / "pid",
        config_path=base_dir / "run_config.json",
    )


def _ensure_run_dir(paths: RunPaths) -> None:
    paths.base_dir.mkdir(parents=True, exist_ok=True)


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _initial_state(config: BatchRunConfig) -> dict[str, Any]:
    workers = {
        str(worker_id): {
            "status": "idle",
            "file": None,
            "started_at": None,
            "started_at_epoch": None,
            "last_result": None,
        }
        for worker_id in range(1, config.workers + 1)
    }
    return {
        "run_id": config.run_id,
        "mode": config.mode,
        "status": "running",
        "started_at": _utc_now_iso(),
        "ended_at": None,
        "updated_at": _utc_now_iso(),
        "error": None,
        "config": {
            "workers": config.workers,
            "timeout_seconds": config.timeout_seconds,
            "retries": config.retries,
            "validate": config.validate,
            "resume": config.resume,
            "store": config.store,
            "model": config.model,
            "reasoning": config.reasoning,
            "exam_type": config.exam_type,
            "suffix": config.suffix,
            "output_dir": config.output_dir,
            "db_path": config.db_path,
            "status_interval_seconds": config.status_interval_seconds,
            "manifest_path": config.manifest_path,
        },
        "progress": {
            "total": len(config.inputs),
            "done": 0,
            "ok": 0,
            "skipped": 0,
            "failed": 0,
            "timeout": 0,
        },
        "workers": workers,
    }


def _render_status(state: dict[str, Any]) -> str:
    progress = state["progress"]
    now_epoch = _now_epoch()
    lines = [
        (
            "RUN "
            f"id={state['run_id']} status={state['status']} "
            f"done={progress['done']}/{progress['total']} "
            f"ok={progress['ok']} skipped={progress['skipped']} "
            f"failed={progress['failed']} timeout={progress['timeout']}"
        ),
        f"UPDATED {state.get('updated_at')}",
    ]
    for worker_id, worker in sorted(state["workers"].items(), key=lambda item: int(item[0])):
        if worker["status"] == "running":
            started = worker.get("started_at_epoch")
            elapsed = (now_epoch - started) if isinstance(started, (int, float)) else 0.0
            lines.append(f"w{worker_id}: running {worker['file']} ({elapsed:.1f}s)")
        else:
            lines.append(f"w{worker_id}: idle")
    return "\n".join(lines)


async def _run_batch_extraction_runtime(
    report_text: str,
    *,
    exam_type: str | None,
    model: str | None,
    reasoning: str | None,
    validate: bool,
    store: ExtractionStore | None,
    db_path: Path | None,
    source_ref: str | None,
):
    """Run shared extraction runtime and unwrap CLI/batch-oriented tuple."""
    result = await run_extraction_runtime(
        report_text,
        exam_type=exam_type,
        model=model,
        reasoning=reasoning,
        validate=validate,
        reliability_mode="strict",
        store=store,
        db_path=db_path,
        source_ref=source_ref,
    )
    return result.extraction, result.validation_result, result.storage_metadata


async def _process_one_file(
    source_path: Path,
    *,
    config: BatchRunConfig,
    output_dir: Path | None,
    store: ExtractionStore | None,
) -> dict[str, Any]:
    started_monotonic = time.monotonic()
    output_path = _resolve_output_path(source_path, output_dir, config.suffix)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    if config.resume and output_path.exists():
        return {
            "source_path": str(source_path),
            "output_path": str(output_path),
            "status": "skipped",
            "duration_seconds": time.monotonic() - started_monotonic,
            "findings_count": None,
            "non_finding_count": None,
            "error": None,
            "report_id": None,
            "extraction_id": None,
        }

    report_text = source_path.read_text(encoding="utf-8")
    last_error: str | None = None

    for attempt in range(config.retries + 1):
        try:
            extraction, validation_result, storage_metadata = await asyncio.wait_for(
                _run_batch_extraction_runtime(
                    report_text,
                    exam_type=config.exam_type,
                    model=config.model,
                    reasoning=config.reasoning,
                    validate=config.validate,
                    store=store,
                    db_path=Path(config.db_path),
                    source_ref=str(source_path),
                ),
                timeout=config.timeout_seconds,
            )

            payload = extraction.model_dump(mode="json")
            if validation_result is not None:
                payload["_validation"] = validation_result.model_dump(mode="json")
            if storage_metadata is not None:
                storage_dict: dict[str, Any] = {
                    "db_path": storage_metadata.db_path,
                    "report_id": storage_metadata.report_id,
                    "report_seen_before": storage_metadata.report_seen_before,
                    "extraction_id": storage_metadata.extraction_id,
                    "model_name": storage_metadata.model_name,
                    "reasoning_effort": storage_metadata.reasoning_effort,
                    "extracted_at": storage_metadata.extracted_at,
                }
                if storage_metadata.usage is not None:
                    storage_dict["usage"] = storage_metadata.usage.model_dump(mode="json")
                payload["_storage"] = storage_dict
            output_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            return {
                "source_path": str(source_path),
                "output_path": str(output_path),
                "status": "ok",
                "duration_seconds": time.monotonic() - started_monotonic,
                "findings_count": len(extraction.findings),
                "non_finding_count": len(extraction.non_finding_text),
                "error": None,
                "report_id": storage_metadata.report_id if storage_metadata else None,
                "extraction_id": storage_metadata.extraction_id if storage_metadata else None,
            }
        except TimeoutError:
            last_error = f"timed out after {config.timeout_seconds}s"
            if attempt == config.retries:
                return {
                    "source_path": str(source_path),
                    "output_path": str(output_path),
                    "status": "timeout",
                    "duration_seconds": time.monotonic() - started_monotonic,
                    "findings_count": None,
                    "non_finding_count": None,
                    "error": last_error,
                    "report_id": None,
                    "extraction_id": None,
                }
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)
            if attempt == config.retries:
                return {
                    "source_path": str(source_path),
                    "output_path": str(output_path),
                    "status": "failed",
                    "duration_seconds": time.monotonic() - started_monotonic,
                    "findings_count": None,
                    "non_finding_count": None,
                    "error": last_error,
                    "report_id": None,
                    "extraction_id": None,
                }

    return {
        "source_path": str(source_path),
        "output_path": str(output_path),
        "status": "failed",
        "duration_seconds": time.monotonic() - started_monotonic,
        "findings_count": None,
        "non_finding_count": None,
        "error": last_error or "unknown error",
        "report_id": None,
        "extraction_id": None,
    }


async def _run_engine(config: BatchRunConfig, *, emit: bool = True) -> int:
    run_paths = _run_paths(Path(config.run_dir), config.run_id)
    _ensure_run_dir(run_paths)

    output_dir = Path(config.output_dir) if config.output_dir else None
    manifest_path = Path(config.manifest_path) if config.manifest_path else None
    inputs = [Path(path) for path in config.inputs]

    state = _initial_state(config)
    _write_json_atomic(run_paths.state_path, state)

    store: ExtractionStore | None = ExtractionStore(Path(config.db_path)) if config.store else None
    if store is not None:
        migration_error = await store.check_migration_current()
        if migration_error is not None:
            await store.close()
            error_msg = f"{migration_error} (IPL_DB_PATH={config.db_path})"
            state["status"] = "failed"
            state["error"] = error_msg
            state["ended_at"] = _utc_now_iso()
            _write_json_atomic(run_paths.state_path, state)
            raise click.ClickException(error_msg)
        await store.init()

    queue: asyncio.Queue[Path | None] = asyncio.Queue()
    for source_path in inputs:
        queue.put_nowait(source_path)
    for _ in range(config.workers):
        queue.put_nowait(None)

    lock = asyncio.Lock()
    stop_event = asyncio.Event()

    async def persist_state() -> None:
        state["updated_at"] = _utc_now_iso()
        _write_json_atomic(run_paths.state_path, state)

    async def worker(worker_id: int) -> None:
        worker_key = str(worker_id)
        while True:
            source_path = await queue.get()
            if source_path is None:
                async with lock:
                    state["workers"][worker_key]["status"] = "idle"
                    state["workers"][worker_key]["file"] = None
                    state["workers"][worker_key]["started_at"] = None
                    state["workers"][worker_key]["started_at_epoch"] = None
                    await persist_state()
                queue.task_done()
                return

            async with lock:
                state["workers"][worker_key]["status"] = "running"
                state["workers"][worker_key]["file"] = source_path.name
                state["workers"][worker_key]["started_at"] = _utc_now_iso()
                state["workers"][worker_key]["started_at_epoch"] = _now_epoch()
                await persist_state()

            result = await _process_one_file(
                source_path,
                config=config,
                output_dir=output_dir,
                store=store,
            )

            async with lock:
                _append_jsonl(run_paths.results_path, result)
                status = result["status"]
                state["progress"][status] += 1
                state["progress"]["done"] += 1
                state["workers"][worker_key]["status"] = "idle"
                state["workers"][worker_key]["file"] = None
                state["workers"][worker_key]["started_at"] = None
                state["workers"][worker_key]["started_at_epoch"] = None
                state["workers"][worker_key]["last_result"] = {
                    "status": status,
                    "source_path": result["source_path"],
                    "duration_seconds": result["duration_seconds"],
                }
                await persist_state()
                if emit:
                    if status == "ok":
                        click.echo(
                            f"[OK] {Path(result['source_path']).name} -> "
                            f"{Path(result['output_path']).name} "
                            f"({result['findings_count']} findings, {result['duration_seconds']:.1f}s)"
                        )
                    elif status == "skipped":
                        click.echo(f"[SKIP] {Path(result['output_path']).name} exists")
                    else:
                        click.echo(
                            f"[{status.upper()}] {Path(result['source_path']).name}: "
                            f"{result['error'] or 'unknown error'}"
                        )
            queue.task_done()

    async def reporter() -> None:
        while not stop_event.is_set():
            await asyncio.sleep(config.status_interval_seconds)
            async with lock:
                if state["status"] != "running":
                    continue
                if emit:
                    click.echo(_render_status(state))

    reporter_task = asyncio.create_task(reporter())
    workers = [asyncio.create_task(worker(worker_id)) for worker_id in range(1, config.workers + 1)]
    error: str | None = None
    try:
        await queue.join()
        await asyncio.gather(*workers)
    except Exception as exc:  # noqa: BLE001
        error = str(exc)
        raise
    finally:
        stop_event.set()
        await reporter_task
        if store is not None:
            await store.close()

        async with lock:
            if error:
                state["status"] = "failed"
                state["error"] = error
            elif state["progress"]["failed"] or state["progress"]["timeout"]:
                state["status"] = "completed_with_errors"
            else:
                state["status"] = "completed"
            state["ended_at"] = _utc_now_iso()
            await persist_state()

    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(
            run_paths.results_path.read_text(encoding="utf-8"), encoding="utf-8"
        )

    if emit:
        progress = state["progress"]
        click.echo(
            "DONE "
            f"run_id={config.run_id} "
            f"total={progress['total']} done={progress['done']} "
            f"ok={progress['ok']} skipped={progress['skipped']} "
            f"failed={progress['failed']} timeout={progress['timeout']}"
        )
    return 1 if state["progress"]["failed"] or state["progress"]["timeout"] else 0


_run_engine_sync = runnify(_run_engine)


def _build_config_dict(config: BatchRunConfig) -> dict[str, Any]:
    return {
        "run_id": config.run_id,
        "mode": config.mode,
        "inputs": config.inputs,
        "output_dir": config.output_dir,
        "suffix": config.suffix,
        "model": config.model,
        "reasoning": config.reasoning,
        "exam_type": config.exam_type,
        "workers": config.workers,
        "timeout_seconds": config.timeout_seconds,
        "retries": config.retries,
        "validate": config.validate,
        "resume": config.resume,
        "store": config.store,
        "db_path": config.db_path,
        "status_interval_seconds": config.status_interval_seconds,
        "manifest_path": config.manifest_path,
        "run_dir": config.run_dir,
    }


def _config_from_dict(payload: dict[str, Any]) -> BatchRunConfig:
    return BatchRunConfig(
        run_id=payload["run_id"],
        mode=payload["mode"],
        inputs=list(payload["inputs"]),
        output_dir=payload.get("output_dir"),
        suffix=payload["suffix"],
        model=payload["model"],
        reasoning=payload.get("reasoning"),
        exam_type=payload.get("exam_type"),
        workers=int(payload["workers"]),
        timeout_seconds=int(payload["timeout_seconds"]),
        retries=int(payload["retries"]),
        validate=bool(payload["validate"]),
        resume=bool(payload["resume"]),
        store=bool(payload["store"]),
        db_path=payload["db_path"],
        status_interval_seconds=float(payload["status_interval_seconds"]),
        manifest_path=payload.get("manifest_path"),
        run_dir=payload["run_dir"],
    )


def _resolve_run_options(
    *,
    mode: RunMode,
    workers: int | None,
    timeout_seconds: int | None,
    retries: int | None,
    status_interval_seconds: float | None,
    resume: bool | None,
    suffix: str | None,
    model: str | None,
    reasoning: str | None,
    exam_type: str | None,
    validate: bool,
    store: bool,
    db_path: Path | None,
    output_dir: Path | None,
    manifest: Path | None,
    run_dir: Path | None,
    run_id: str | None,
    input_files: list[Path],
) -> BatchRunConfig:
    settings = get_settings()
    resolved_model = model or settings.default_model
    validate_model_id(resolved_model)
    effective_reasoning = resolve_runtime_reasoning(
        resolved_model,
        reasoning,
        allow_unknown_model_reasoning=settings.allow_unknown_model_reasoning,
    )

    resolved_workers = workers if workers is not None else settings.batch_workers
    resolved_timeout = (
        timeout_seconds if timeout_seconds is not None else settings.batch_timeout_seconds
    )
    resolved_retries = retries if retries is not None else settings.batch_retries
    resolved_status_interval = (
        status_interval_seconds
        if status_interval_seconds is not None
        else settings.batch_status_interval_seconds
    )
    resolved_resume = resume if resume is not None else settings.batch_resume
    resolved_suffix = suffix or settings.batch_output_suffix

    if not resolved_suffix.startswith("."):
        raise click.ClickException("Output suffix must start with '.' (example: .extracted.json)")

    resolved_db_path = (db_path or settings.db_path).resolve()
    resolved_run_dir = (run_dir or settings.batch_run_dir).resolve()
    resolved_output_dir = output_dir.resolve() if output_dir else None
    resolved_manifest = manifest.resolve() if manifest else None
    resolved_run_id = run_id or _make_run_id()
    if not _RUN_ID_PATTERN.match(resolved_run_id):
        raise click.ClickException(
            "Invalid run id. Use 1-128 chars from [A-Za-z0-9._-], starting with alphanumeric."
        )

    return BatchRunConfig(
        run_id=resolved_run_id,
        mode=mode,
        inputs=[str(path) for path in input_files],
        output_dir=str(resolved_output_dir) if resolved_output_dir else None,
        suffix=resolved_suffix,
        model=resolved_model,
        reasoning=effective_reasoning,
        exam_type=exam_type,
        workers=resolved_workers,
        timeout_seconds=resolved_timeout,
        retries=resolved_retries,
        validate=validate,
        resume=resolved_resume,
        store=store,
        db_path=str(resolved_db_path),
        status_interval_seconds=resolved_status_interval,
        manifest_path=str(resolved_manifest) if resolved_manifest else None,
        run_dir=str(resolved_run_dir),
    )


@click.group(name="finding-extractor-batch")
def cli() -> None:
    """Batch extraction workflows (local in-process v1)."""
    settings = get_settings()
    logfire_enabled = configure_logfire(runtime="cli")
    setup_logging(settings, include_logfire_processor=logfire_enabled)


@cli.command("run")
@click.argument("inputs", nargs=-1, type=click.Path(path_type=Path, exists=True))
@click.option(
    "--glob",
    "glob_pattern",
    default="*.txt",
    show_default=True,
    help="Pattern for directory inputs.",
)
@click.option(
    "--recursive/--no-recursive",
    default=False,
    show_default=True,
    help="Use recursive globbing for directory inputs.",
)
@click.option(
    "--mode",
    type=click.Choice(["interactive", "detached"], case_sensitive=False),
    default="interactive",
    show_default=True,
    help="Runtime mode.",
)
@click.option("--run-id", default=None, help="Optional run id (defaults to generated id).")
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory for output JSON files.",
)
@click.option("--suffix", default=None, help="Output suffix (defaults from settings).")
@click.option("--model", default=None, help="Model id override.")
@click.option(
    "--reasoning",
    type=click.Choice(["none", "minimal", "low", "medium", "high"], case_sensitive=False),
    default=None,
    help="Reasoning level override.",
)
@click.option("--exam-type", default=None, help="Optional exam description applied to all files.")
@click.option(
    "--workers", type=click.IntRange(min=1, max=64), default=None, help="Concurrent worker count."
)
@click.option(
    "--timeout-seconds", type=click.IntRange(min=10), default=None, help="Per-file timeout."
)
@click.option(
    "--retries", type=click.IntRange(min=0, max=10), default=None, help="Retries per file."
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
@click.option(
    "--validate/--no-validate",
    default=True,
    show_default=True,
    help="Run post-extraction coverage analysis (verbatim checking is handled by the agent's output validator).",
)
@click.option(
    "--resume/--no-resume", default=None, help="Skip existing outputs (defaults from settings)."
)
@click.option(
    "--store/--no-store",
    default=False,
    show_default=True,
    help="Persist report/extraction rows to SQLite.",
)
@click.option(
    "--db-path", type=click.Path(path_type=Path), default=None, help="SQLite path for --store."
)
@click.option(
    "--status-interval-seconds", type=float, default=None, help="How often to print status updates."
)
@click.option(
    "--manifest",
    type=click.Path(path_type=Path),
    default=None,
    help="Optional JSONL copy of per-file results.",
)
@click.option(
    "--run-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory for run state files.",
)
def run_command(
    inputs: tuple[Path, ...],
    glob_pattern: str,
    recursive: bool,
    mode: str,
    run_id: str | None,
    output_dir: Path | None,
    suffix: str | None,
    model: str | None,
    reasoning: str | None,
    exam_type: str | None,
    workers: int | None,
    timeout_seconds: int | None,
    retries: int | None,
    max_predicted_runtime_seconds: int | None,
    allow_slow: bool,
    validate: bool,
    resume: bool | None,
    store: bool,
    db_path: Path | None,
    status_interval_seconds: float | None,
    manifest: Path | None,
    run_dir: Path | None,
) -> None:
    """Run batch extraction over files or directories."""
    if not inputs:
        raise click.ClickException("Provide at least one file or directory input.")

    input_files = _collect_input_files(inputs, glob_pattern=glob_pattern, recursive=recursive)
    if not input_files:
        raise click.ClickException("No input files matched.")

    config = _resolve_run_options(
        mode=mode,  # type: ignore[arg-type]
        workers=workers,
        timeout_seconds=timeout_seconds,
        retries=retries,
        status_interval_seconds=status_interval_seconds,
        resume=resume,
        suffix=suffix,
        model=model,
        reasoning=reasoning,
        exam_type=exam_type,
        validate=validate,
        store=store,
        db_path=db_path,
        output_dir=output_dir,
        manifest=manifest,
        run_dir=run_dir,
        run_id=run_id,
        input_files=input_files,
    )
    resolved_max_predicted_runtime = (
        max_predicted_runtime_seconds
        if max_predicted_runtime_seconds is not None
        else DEFAULT_MAX_PREDICTED_RUNTIME_SECONDS
    )
    preflight_line, preflight_error, preflight_warning = build_runtime_preflight(
        command_label="BATCH",
        item_label="inputs",
        item_count=len(config.inputs),
        workers=config.workers,
        timeout_seconds=config.timeout_seconds,
        retries=config.retries,
        budget_seconds=resolved_max_predicted_runtime,
        allow_slow=allow_slow,
    )
    click.echo(preflight_line)
    if preflight_error:
        raise click.ClickException(preflight_error)
    if preflight_warning:
        click.echo(preflight_warning, err=True)

    resolved_output_dir = Path(config.output_dir) if config.output_dir else None
    _validate_output_collisions(input_files, output_dir=resolved_output_dir, suffix=config.suffix)
    paths = _run_paths(Path(config.run_dir), config.run_id)
    _ensure_run_dir(paths)
    _write_json_atomic(paths.config_path, _build_config_dict(config))

    click.echo(
        "BATCH "
        f"run_id={config.run_id} mode={config.mode} inputs={len(config.inputs)} "
        f"workers={config.workers} model={config.model} reasoning={config.reasoning or 'default'}"
    )

    if config.mode == "detached":
        starting_state = _initial_state(config)
        starting_state["status"] = "starting"
        _write_json_atomic(paths.state_path, starting_state)
        with paths.log_path.open("a", encoding="utf-8") as log_handle:
            cmd = [
                sys.executable,
                "-m",
                "finding_extractor.batch_cli",
                "_run-child",
                "--run-config",
                str(paths.config_path),
            ]
            proc = subprocess.Popen(  # noqa: S603
                cmd,
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                cwd=os.getcwd(),
            )
        paths.pid_path.write_text(str(proc.pid), encoding="utf-8")
        click.echo(f"STARTED run_id={config.run_id} pid={proc.pid}")
        click.echo(
            f"STATUS  finding-extractor-batch status --run-id {config.run_id} --run-dir {config.run_dir}"
        )
        return

    exit_code = _run_engine_sync(config=config, emit=True)
    if exit_code:
        raise SystemExit(exit_code)


@cli.command("status")
@click.option("--run-id", required=True, help="Run id to inspect.")
@click.option(
    "--run-dir",
    type=click.Path(path_type=Path),
    default=None,
    help="Directory containing run states.",
)
@click.option(
    "--watch/--no-watch",
    default=False,
    show_default=True,
    help="Continuously refresh status output.",
)
@click.option(
    "--interval-seconds", type=float, default=None, help="Watch interval (defaults from settings)."
)
def status_command(
    run_id: str, run_dir: Path | None, watch: bool, interval_seconds: float | None
) -> None:
    """Show batch run status from local state file."""
    settings = get_settings()
    resolved_run_dir = (run_dir or settings.batch_run_dir).resolve()
    resolved_interval = (
        interval_seconds if interval_seconds is not None else settings.batch_status_interval_seconds
    )
    paths = _run_paths(resolved_run_dir, run_id)
    if not paths.state_path.exists():
        raise click.ClickException(f"Run state not found: {paths.state_path}")

    def print_once() -> dict:
        state = _load_json(paths.state_path)
        click.echo(_render_status(state))
        if state.get("error"):
            click.echo(f"ERROR {state['error']}")
        if state["status"] in _TERMINAL_STATUSES:
            click.echo(f"ENDED {state.get('ended_at')}")
        return state

    if not watch:
        print_once()
        return

    while True:
        state = print_once()
        if state["status"] in _TERMINAL_STATUSES:
            return
        time.sleep(resolved_interval)


@cli.command("_run-child", hidden=True)
@click.option("--run-config", type=click.Path(path_type=Path, exists=True), required=True)
def run_child_command(run_config: Path) -> None:
    """Internal: execute a detached run from a serialized config."""
    config_payload = _load_json(run_config)
    config = _config_from_dict(config_payload)
    exit_code = _run_engine_sync(config=config, emit=True)
    if exit_code:
        raise SystemExit(exit_code)


if __name__ == "__main__":
    cli()
