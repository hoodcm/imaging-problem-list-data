"""Tests for batch extraction CLI."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path

from click.testing import CliRunner

from finding_extractor.batch_cli import cli
from finding_extractor.models import ExamInfo, ExtractedFinding, ReportExtraction


def test_batch_run_interactive_writes_outputs_and_state(monkeypatch):
    """Interactive run should produce extracted files and terminal state metadata."""

    async def fake_run_extraction_pipeline(
        report_text,
        *,
        exam_type,
        model,
        reasoning,
        validate,
        store,
        db_path,
        source_ref,
    ):
        _ = (exam_type, model, reasoning, validate, store, db_path, source_ref)
        return (
            ReportExtraction(
                exam_info=ExamInfo(study_description="Chest XR"),
                findings=[
                    ExtractedFinding(
                        finding_name="pleural effusion",
                        presence="absent",
                        report_text=report_text.strip(),
                    )
                ],
                non_finding_text=[],
            ),
            None,
            None,
        )

    monkeypatch.setattr(
        "finding_extractor.batch_cli.run_extraction_pipeline",
        fake_run_extraction_pipeline,
    )

    runner = CliRunner()
    with runner.isolated_filesystem():
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "a.txt").write_text("No pleural effusion.", encoding="utf-8")
        (reports_dir / "b.txt").write_text("No pneumothorax.", encoding="utf-8")

        run_id = "batch-test-1"
        result = runner.invoke(
            cli,
            [
                "run",
                str(reports_dir),
                "--glob",
                "*.txt",
                "--mode",
                "interactive",
                "--workers",
                "2",
                "--run-id",
                run_id,
                "--run-dir",
                ".runs",
                "--model",
                "openai:gpt-5-mini",
                "--reasoning",
                "medium",
            ],
        )

        assert result.exit_code == 0
        assert (reports_dir / "a.extracted.json").exists()
        assert (reports_dir / "b.extracted.json").exists()

        state_path = Path(".runs") / run_id / "state.json"
        results_path = Path(".runs") / run_id / "results.jsonl"
        assert state_path.exists()
        assert results_path.exists()

        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "completed"
        assert state["progress"]["total"] == 2
        assert state["progress"]["done"] == 2
        assert state["progress"]["ok"] == 2

        results = [line for line in results_path.read_text(encoding="utf-8").splitlines() if line]
        assert len(results) == 2


def test_batch_status_shows_worker_elapsed_time():
    """Status output should include live elapsed runtime for running workers."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        run_id = "batch-test-status"
        run_dir = Path(".runs") / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        started = time.time() - 12.0

        state = {
            "run_id": run_id,
            "mode": "interactive",
            "status": "running",
            "started_at": "2026-02-11T00:00:00+00:00",
            "ended_at": None,
            "updated_at": "2026-02-11T00:00:10+00:00",
            "error": None,
            "config": {},
            "progress": {"total": 2, "done": 1, "ok": 1, "skipped": 0, "failed": 0, "timeout": 0},
            "workers": {
                "1": {
                    "status": "running",
                    "file": "a.txt",
                    "started_at": "2026-02-11T00:00:05+00:00",
                    "started_at_epoch": started,
                    "last_result": None,
                },
                "2": {
                    "status": "idle",
                    "file": None,
                    "started_at": None,
                    "started_at_epoch": None,
                    "last_result": None,
                },
            },
        }
        (run_dir / "state.json").write_text(json.dumps(state, indent=2), encoding="utf-8")

        result = runner.invoke(
            cli,
            [
                "status",
                "--run-id",
                run_id,
                "--run-dir",
                ".runs",
            ],
        )

        assert result.exit_code == 0
        assert "w1: running a.txt" in result.output
        match = re.search(r"w1: running a\.txt \((\d+\.\d+)s\)", result.output)
        assert match is not None
        assert float(match.group(1)) >= 10.0


def test_batch_run_rejects_invalid_run_id(monkeypatch):
    """Run id should be restricted to safe filesystem-friendly characters."""

    async def fake_extract_findings(report_text, exam_description=None, model=None, reasoning=None):
        _ = (report_text, exam_description, model, reasoning)
        return ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[],
            non_finding_text=[],
        )

    monkeypatch.setattr("finding_extractor.extraction_pipeline.extract_findings", fake_extract_findings)

    runner = CliRunner()
    with runner.isolated_filesystem():
        reports_dir = Path("reports")
        reports_dir.mkdir(parents=True, exist_ok=True)
        (reports_dir / "a.txt").write_text("No pleural effusion.", encoding="utf-8")

        result = runner.invoke(
            cli,
            [
                "run",
                str(reports_dir),
                "--glob",
                "*.txt",
                "--run-id",
                "../bad-id",
            ],
        )
        assert result.exit_code != 0
        assert "Invalid run id" in result.output


def test_batch_status_watch_waits_while_starting():
    """Watch mode should treat 'starting' as active and wait for terminal state."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        run_id = "batch-test-watch"
        run_dir = Path(".runs") / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        state_path = run_dir / "state.json"
        state = {
            "run_id": run_id,
            "mode": "detached",
            "status": "starting",
            "started_at": "2026-02-11T00:00:00+00:00",
            "ended_at": None,
            "updated_at": "2026-02-11T00:00:00+00:00",
            "error": None,
            "config": {},
            "progress": {"total": 1, "done": 0, "ok": 0, "skipped": 0, "failed": 0, "timeout": 0},
            "workers": {
                "1": {
                    "status": "idle",
                    "file": None,
                    "started_at": None,
                    "started_at_epoch": None,
                    "last_result": None,
                },
            },
        }
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")

        def _complete_soon() -> None:
            time.sleep(0.05)
            updated = json.loads(state_path.read_text(encoding="utf-8"))
            updated["status"] = "completed"
            updated["ended_at"] = "2026-02-11T00:00:01+00:00"
            updated["updated_at"] = "2026-02-11T00:00:01+00:00"
            updated["progress"]["done"] = 1
            updated["progress"]["ok"] = 1
            state_path.write_text(json.dumps(updated, indent=2), encoding="utf-8")

        t = threading.Thread(target=_complete_soon, daemon=True)
        t.start()
        result = runner.invoke(
            cli,
            [
                "status",
                "--run-id",
                run_id,
                "--run-dir",
                ".runs",
                "--watch",
                "--interval-seconds",
                "0.01",
            ],
        )
        t.join(timeout=1)

        assert result.exit_code == 0
        assert "status=starting" in result.output
        assert "status=completed" in result.output
