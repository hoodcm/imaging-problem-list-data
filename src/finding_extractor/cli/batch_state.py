"""Run-state directory/JSON helpers and status tracking for batch CLI."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

RunMode = Literal["interactive", "detached"]
_TERMINAL_STATUSES = {"completed", "completed_with_errors", "failed"}


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


def run_paths(run_dir: Path, run_id: str) -> RunPaths:
    base_dir = run_dir / run_id
    return RunPaths(
        base_dir=base_dir,
        state_path=base_dir / "state.json",
        results_path=base_dir / "results.jsonl",
        log_path=base_dir / "log.txt",
        pid_path=base_dir / "pid",
        config_path=base_dir / "run_config.json",
    )


def ensure_run_dir(paths: RunPaths) -> None:
    paths.base_dir.mkdir(parents=True, exist_ok=True)


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def initial_state(config: Any) -> dict[str, Any]:
    """Create initial state.json structure from a BatchRunConfig."""
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


def render_status(state: dict[str, Any]) -> str:
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
