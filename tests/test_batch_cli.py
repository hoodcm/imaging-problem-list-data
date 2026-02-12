"""Tests for batch extraction CLI."""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from finding_extractor.batch_cli import BatchRunConfig, _process_one_file, _resolve_run_options, cli
from finding_extractor.extraction_pipeline import StorageMetadata
from finding_extractor.models import ExamInfo, ExtractedFinding, ExtractionUsage, ReportExtraction


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


def test_batch_cli_wires_structured_logging_setup(monkeypatch):
    """Batch CLI startup should configure logfire first, then structured logging."""
    calls: dict[str, object] = {}
    runner = CliRunner()

    def fake_configure_logfire(*, runtime, enabled_override=None, fastapi_app=None):
        _ = (enabled_override, fastapi_app)
        calls["runtime"] = runtime
        return True

    def fake_setup_logging(settings, *, include_logfire_processor):
        calls["settings"] = settings
        calls["include_logfire_processor"] = include_logfire_processor

    monkeypatch.setattr("finding_extractor.batch_cli.configure_logfire", fake_configure_logfire)
    monkeypatch.setattr("finding_extractor.batch_cli.setup_logging", fake_setup_logging)

    with runner.isolated_filesystem():
        run_id = "batch-test-logging"
        run_dir = Path(".runs") / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "state.json").write_text(
            json.dumps(
                {
                    "run_id": run_id,
                    "mode": "interactive",
                    "status": "completed",
                    "started_at": "2026-02-11T00:00:00+00:00",
                    "ended_at": "2026-02-11T00:00:01+00:00",
                    "updated_at": "2026-02-11T00:00:01+00:00",
                    "error": None,
                    "config": {},
                    "progress": {
                        "total": 0,
                        "done": 0,
                        "ok": 0,
                        "skipped": 0,
                        "failed": 0,
                        "timeout": 0,
                    },
                    "workers": {},
                }
            ),
            encoding="utf-8",
        )

        result = runner.invoke(cli, ["status", "--run-id", run_id, "--run-dir", ".runs"])

    assert result.exit_code == 0
    assert calls["runtime"] == "cli"
    assert calls["include_logfire_processor"] is True
    assert calls["settings"] is not None


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

    monkeypatch.setattr(
        "finding_extractor.extraction_pipeline.extract_findings", fake_extract_findings
    )

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


class TestReasoningPreflight:
    """Reasoning compatibility is checked at batch start, not per-file."""

    def test_resolve_run_options_rejects_incompatible_reasoning(self, tmp_path: Path):
        """Invalid reasoning for a provider should raise at resolve time."""
        report = tmp_path / "report.txt"
        report.write_text("Normal chest.")

        with pytest.raises(ValueError, match="not supported by ollama"):
            _resolve_run_options(
                mode="interactive",
                workers=1,
                timeout_seconds=60,
                retries=0,
                status_interval_seconds=30.0,
                resume=False,
                suffix=".extracted.json",
                model="ollama:llama4",
                reasoning="high",
                exam_type=None,
                validate=False,
                store=False,
                db_path=tmp_path / "test.db",
                output_dir=None,
                manifest=None,
                run_dir=tmp_path / "runs",
                run_id="test-run",
                input_files=[report],
            )

    def test_resolve_run_options_accepts_valid_reasoning(self, tmp_path: Path):
        """Valid reasoning for a provider should succeed."""
        report = tmp_path / "report.txt"
        report.write_text("Normal chest.")

        config = _resolve_run_options(
            mode="interactive",
            workers=1,
            timeout_seconds=60,
            retries=0,
            status_interval_seconds=30.0,
            resume=False,
            suffix=".extracted.json",
            model="openai:gpt-5-mini",
            reasoning="medium",
            exam_type=None,
            validate=False,
            store=False,
            db_path=tmp_path / "test.db",
            output_dir=None,
            manifest=None,
            run_dir=tmp_path / "runs",
            run_id="test-run",
            input_files=[report],
        )
        assert config.reasoning == "medium"

    def test_resolve_run_options_skips_validation_when_reasoning_is_none(self, tmp_path: Path):
        """When reasoning is None (not specified), no validation should occur."""
        report = tmp_path / "report.txt"
        report.write_text("Normal chest.")

        config = _resolve_run_options(
            mode="interactive",
            workers=1,
            timeout_seconds=60,
            retries=0,
            status_interval_seconds=30.0,
            resume=False,
            suffix=".extracted.json",
            model="ollama:llama4",
            reasoning=None,
            exam_type=None,
            validate=False,
            store=False,
            db_path=tmp_path / "test.db",
            output_dir=None,
            manifest=None,
            run_dir=tmp_path / "runs",
            run_id="test-run",
            input_files=[report],
        )
        assert config.reasoning is None


class TestUsageInOutput:
    """Usage data is included in batch _storage output."""

    @pytest.mark.asyncio
    async def test_process_one_file_includes_usage_in_storage(self, tmp_path: Path):
        """When storage_metadata has usage, it should appear in the output JSON."""
        report = tmp_path / "report.txt"
        report.write_text("Normal chest radiograph.")

        usage = ExtractionUsage(
            requests=1,
            input_tokens=500,
            output_tokens=200,
            cache_read_tokens=50,
            cache_write_tokens=100,
            duration_ms=1234,
        )
        storage = StorageMetadata(
            db_path=str(tmp_path / "test.db"),
            report_id="r1",
            report_seen_before=False,
            extraction_id="e1",
            model_name="openai:gpt-5-mini",
            reasoning_effort=None,
            extracted_at="2026-02-11T00:00:00+00:00",
            usage=usage,
        )
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[
                ExtractedFinding(
                    finding_name="pleural effusion",
                    presence="absent",
                    report_text="Normal chest radiograph.",
                )
            ],
        )

        async def fake_pipeline(*args, **kwargs):
            return extraction, None, storage

        config = BatchRunConfig(
            run_id="test",
            mode="interactive",
            inputs=[str(report)],
            output_dir=str(tmp_path / "out"),
            suffix=".extracted.json",
            model="openai:gpt-5-mini",
            reasoning=None,
            exam_type=None,
            workers=1,
            timeout_seconds=60,
            retries=0,
            validate=False,
            resume=False,
            store=True,
            db_path=str(tmp_path / "test.db"),
            status_interval_seconds=30.0,
            manifest_path=None,
            run_dir=str(tmp_path / "runs"),
        )

        with patch(
            "finding_extractor.batch_cli.run_extraction_pipeline", side_effect=fake_pipeline
        ):
            result = await _process_one_file(
                report,
                config=config,
                output_dir=tmp_path / "out",
                store=None,
            )

        assert result["status"] == "ok"
        output_path = Path(result["output_path"])
        payload = json.loads(output_path.read_text())
        assert "_storage" in payload
        assert "usage" in payload["_storage"]
        assert payload["_storage"]["usage"]["input_tokens"] == 500
        assert payload["_storage"]["usage"]["output_tokens"] == 200
        assert payload["_storage"]["usage"]["duration_ms"] == 1234

    @pytest.mark.asyncio
    async def test_process_one_file_omits_usage_when_none(self, tmp_path: Path):
        """When storage_metadata has no usage, _storage should not have a usage key."""
        report = tmp_path / "report.txt"
        report.write_text("Normal chest radiograph.")

        storage = StorageMetadata(
            db_path=str(tmp_path / "test.db"),
            report_id="r1",
            report_seen_before=False,
            extraction_id="e1",
            model_name="openai:gpt-5-mini",
            reasoning_effort=None,
            extracted_at="2026-02-11T00:00:00+00:00",
        )
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Chest XR"),
            findings=[
                ExtractedFinding(
                    finding_name="pleural effusion",
                    presence="absent",
                    report_text="Normal chest radiograph.",
                )
            ],
        )

        async def fake_pipeline(*args, **kwargs):
            return extraction, None, storage

        config = BatchRunConfig(
            run_id="test",
            mode="interactive",
            inputs=[str(report)],
            output_dir=str(tmp_path / "out"),
            suffix=".extracted.json",
            model="openai:gpt-5-mini",
            reasoning=None,
            exam_type=None,
            workers=1,
            timeout_seconds=60,
            retries=0,
            validate=False,
            resume=False,
            store=True,
            db_path=str(tmp_path / "test.db"),
            status_interval_seconds=30.0,
            manifest_path=None,
            run_dir=str(tmp_path / "runs"),
        )

        with patch(
            "finding_extractor.batch_cli.run_extraction_pipeline", side_effect=fake_pipeline
        ):
            result = await _process_one_file(
                report,
                config=config,
                output_dir=tmp_path / "out",
                store=None,
            )

        assert result["status"] == "ok"
        output_path = Path(result["output_path"])
        payload = json.loads(output_path.read_text())
        assert "_storage" in payload
        assert "usage" not in payload["_storage"]


class TestMigrationPreflight:
    """Migration-revision preflight writes terminal state on failure."""

    def test_batch_run_migration_preflight_writes_failed_state(self, monkeypatch, tmp_path: Path):
        """When --store targets a DB at wrong revision, state.json should be terminal 'failed'."""

        async def fake_check_migration(self) -> str | None:
            return (
                "Database is at revision 17f8ebc6c608, "
                "expected a3f1c8b2d4e6. Run 'task db:migrate' to upgrade."
            )

        monkeypatch.setattr(
            "finding_extractor.store.ExtractionStore.check_migration_current",
            fake_check_migration,
        )

        reports_dir = tmp_path / "reports"
        reports_dir.mkdir()
        (reports_dir / "a.txt").write_text("Normal chest.", encoding="utf-8")

        run_id = "preflight-fail"
        run_dir = tmp_path / "runs"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "run",
                str(reports_dir),
                "--glob",
                "*.txt",
                "--mode",
                "interactive",
                "--run-id",
                run_id,
                "--run-dir",
                str(run_dir),
                "--store",
                "--db-path",
                str(tmp_path / "test.db"),
                "--model",
                "openai:gpt-5-mini",
            ],
        )

        assert result.exit_code != 0
        assert "task db:migrate" in result.output

        state_path = run_dir / run_id / "state.json"
        assert state_path.exists()
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["status"] == "failed"
        assert state["ended_at"] is not None
        assert "expected a3f1c8b2d4e6" in state["error"]
