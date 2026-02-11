"""Tests for the finding extractor CLI."""

import json
from pathlib import Path

from click.testing import CliRunner

from finding_extractor.cli import format_json_output, format_table_output, main
from finding_extractor.extraction_pipeline import StorageMetadata
from finding_extractor.models import (
    ExamInfo,
    ExtractedFinding,
    ExtractionUsage,
    FindingAttribute,
    FindingLocation,
    ReportExtraction,
    ValidationResult,
)


async def _async_none():
    """Coroutine returning None — used to stub check_migration_current."""
    return None


class TestFormatJsonOutput:
    """Test cases for JSON output formatting."""

    def test_basic_json_output(self):
        """Test formatting extraction as JSON."""
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="CT Abdomen"),
            findings=[
                ExtractedFinding(
                    finding_name="test finding",
                    presence="present",
                    report_text="Test text.",
                ),
            ],
        )
        output = format_json_output(extraction)
        assert "CT Abdomen" in output
        assert "test finding" in output
        assert '"presence": "present"' in output

    def test_json_with_validation(self):
        """Test formatting extraction with validation results."""
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="Test"),
        )
        validation = ValidationResult(
            is_valid=True,
            verbatim_errors=[],
            coverage_warnings=[],
        )
        output = format_json_output(extraction, validation)
        assert "_validation" in output
        assert "is_valid" in output


class TestFormatTableOutput:
    """Test cases for table output formatting."""

    def test_basic_table_output(self):
        """Test formatting extraction as table."""
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="CT Abdomen"),
            findings=[
                ExtractedFinding(
                    finding_name="pneumonia",
                    presence="present",
                    report_text="Pneumonia seen.",
                ),
            ],
        )
        output = format_table_output(extraction)
        assert "CT Abdomen" in output
        assert "pneumonia" in output
        assert "PRESENT" in output or "Present" in output

    def test_table_with_attributes(self):
        """Test table output with finding attributes."""
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="CT"),
            findings=[
                ExtractedFinding(
                    finding_name="renal calculus",
                    presence="present",
                    location=FindingLocation(
                        body_region="abdomen",
                        specific_anatomy="right kidney",
                        laterality="right",
                    ),
                    attributes=[
                        FindingAttribute(key="size", value="3 mm"),
                    ],
                    report_text="Stone seen.",
                ),
            ],
        )
        output = format_table_output(extraction)
        assert "renal calculus" in output
        assert "abdomen" in output
        assert "right" in output.lower()
        assert "size=3 mm" in output


class TestCLI:
    """Test cases for CLI commands."""

    def test_cli_help(self):
        """Test CLI help output."""
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "extract structured findings" in result.output.lower()
        assert "--exam-type" in result.output
        assert "--output" in result.output
        assert "--model" in result.output
        assert "--store / --no-store" in result.output

    def test_cli_missing_file(self):
        """Test CLI with missing file."""
        runner = CliRunner()
        result = runner.invoke(main, ["nonexistent.txt"])
        assert result.exit_code != 0

    def test_cli_rejects_disallowed_model_prefix(self):
        """CLI should fail fast when a model id violates policy."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("No pleural effusion.")

            result = runner.invoke(
                main, [str(report_path), "--model", "google-vertex:gemini-3-pro"]
            )
            assert result.exit_code == 1
            assert "google-vertex models are not allowed; use google-gla:*" in result.output

    def test_cli_store_writes_rows_and_outputs_storage_metadata(self, monkeypatch):
        """When --store is used, CLI exposes storage metadata contract in JSON output."""

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
            status_callback=None,
        ):
            _ = (report_text, exam_type, model, reasoning, validate, store, db_path, source_ref)
            return (
                ReportExtraction(
                    exam_info=ExamInfo(study_description="Chest XR"),
                    findings=[
                        ExtractedFinding(
                            finding_name="pleural effusion",
                            presence="absent",
                            report_text="No pleural effusion.",
                        )
                    ],
                ),
                None,
                StorageMetadata(
                    db_path=str(db_path),
                    report_id="r1",
                    report_seen_before=False,
                    extraction_id="e1",
                    model_name="openai:gpt-5-mini",
                    reasoning_effort=None,
                    extracted_at="2026-02-11T00:00:00+00:00",
                ),
            )

        monkeypatch.setattr(
            "finding_extractor.cli.run_extraction_pipeline", fake_run_extraction_pipeline
        )
        monkeypatch.setattr(
            "finding_extractor.store.ExtractionStore.check_migration_current",
            lambda self: _async_none(),
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("No pleural effusion.")
            db_path = Path("cli.sqlite3")

            result = runner.invoke(
                main,
                [str(report_path), "--store", "--db-path", str(db_path), "--format", "json"],
            )

            assert result.exit_code == 0
            payload = json.loads(result.stdout)
            assert "_storage" in payload
            assert payload["_storage"]["db_path"] == str(db_path)
            assert payload["_storage"]["report_seen_before"] is False
            assert payload["_storage"]["model_name"] == "openai:gpt-5-mini"
            assert payload["_storage"]["report_id"]
            assert payload["_storage"]["extraction_id"]
            assert payload["_storage"]["extracted_at"]

    def test_cli_store_json_includes_usage_when_present(self, monkeypatch):
        """When --store is used and usage is available, JSON _storage includes serialized usage."""

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
            status_callback=None,
        ):
            _ = (report_text, exam_type, model, reasoning, validate, store, db_path, source_ref)
            return (
                ReportExtraction(
                    exam_info=ExamInfo(study_description="Chest XR"),
                    findings=[
                        ExtractedFinding(
                            finding_name="pleural effusion",
                            presence="absent",
                            report_text="No pleural effusion.",
                        )
                    ],
                ),
                None,
                StorageMetadata(
                    db_path=str(db_path),
                    report_id="r1",
                    report_seen_before=False,
                    extraction_id="e1",
                    model_name="openai:gpt-5-mini",
                    reasoning_effort=None,
                    extracted_at="2026-02-11T00:00:00+00:00",
                    usage=ExtractionUsage(
                        requests=1,
                        input_tokens=500,
                        output_tokens=200,
                        cache_read_tokens=50,
                        cache_write_tokens=100,
                        duration_ms=1234,
                    ),
                ),
            )

        monkeypatch.setattr(
            "finding_extractor.cli.run_extraction_pipeline", fake_run_extraction_pipeline
        )
        monkeypatch.setattr(
            "finding_extractor.store.ExtractionStore.check_migration_current",
            lambda self: _async_none(),
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("No pleural effusion.")
            db_path = Path("cli.sqlite3")

            result = runner.invoke(
                main,
                [str(report_path), "--store", "--db-path", str(db_path), "--format", "json"],
            )

            assert result.exit_code == 0
            payload = json.loads(result.stdout)
            assert "_storage" in payload
            usage = payload["_storage"]["usage"]
            assert usage is not None
            assert usage["input_tokens"] == 500
            assert usage["output_tokens"] == 200
            assert usage["duration_ms"] == 1234
            assert usage["requests"] == 1

    def test_cli_default_json_has_no_storage_metadata(self, monkeypatch):
        """Without --store, JSON output should not include _storage."""

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
            status_callback=None,
        ):
            _ = (report_text, exam_type, model, reasoning, validate, store, db_path, source_ref)
            return (
                ReportExtraction(
                    exam_info=ExamInfo(study_description="Chest XR"),
                    findings=[
                        ExtractedFinding(
                            finding_name="cardiomegaly",
                            presence="absent",
                            report_text="Cardiomediastinal silhouette is normal.",
                        )
                    ],
                ),
                None,
                None,
            )

        monkeypatch.setattr(
            "finding_extractor.cli.run_extraction_pipeline", fake_run_extraction_pipeline
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("Cardiomediastinal silhouette is normal.")

            result = runner.invoke(main, [str(report_path), "--format", "json"])
            assert result.exit_code == 0
            payload = json.loads(result.stdout)
            assert "_storage" not in payload

    def test_cli_store_marks_second_run_as_seen_before(self, monkeypatch):
        """Running twice against same DB/report should set report_seen_before on second run."""

        counter = {"n": 0}

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
            status_callback=None,
        ):
            _ = (report_text, exam_type, model, reasoning, validate, store, db_path, source_ref)
            counter["n"] += 1
            n = counter["n"]
            return (
                ReportExtraction(
                    exam_info=ExamInfo(study_description="Chest XR"),
                    findings=[
                        ExtractedFinding(
                            finding_name="pleural effusion",
                            presence="absent",
                            report_text="No pleural effusion.",
                        )
                    ],
                ),
                None,
                StorageMetadata(
                    db_path=str(db_path),
                    report_id="same-report-id",
                    report_seen_before=(n > 1),
                    extraction_id=f"e{n}",
                    model_name="openai:gpt-5-mini",
                    reasoning_effort=None,
                    extracted_at=f"2026-02-11T00:00:0{n}+00:00",
                ),
            )

        monkeypatch.setattr(
            "finding_extractor.cli.run_extraction_pipeline", fake_run_extraction_pipeline
        )
        monkeypatch.setattr(
            "finding_extractor.store.ExtractionStore.check_migration_current",
            lambda self: _async_none(),
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("No pleural effusion.")
            db_path = Path("cli.sqlite3")

            first = runner.invoke(
                main,
                [str(report_path), "--store", "--db-path", str(db_path), "--format", "json"],
            )
            second = runner.invoke(
                main,
                [str(report_path), "--store", "--db-path", str(db_path), "--format", "json"],
            )

            assert first.exit_code == 0
            assert second.exit_code == 0

            first_payload = json.loads(first.stdout)
            second_payload = json.loads(second.stdout)
            assert first_payload["_storage"]["report_seen_before"] is False
            assert second_payload["_storage"]["report_seen_before"] is True
            assert first_payload["_storage"]["report_id"] == second_payload["_storage"]["report_id"]
            assert (
                first_payload["_storage"]["extraction_id"]
                != second_payload["_storage"]["extraction_id"]
            )

    def test_cli_table_output_includes_persistence_block_when_store_enabled(self, monkeypatch):
        """Table output includes persistence section when --store is enabled."""

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
            status_callback=None,
        ):
            _ = (report_text, exam_type, model, reasoning, validate, store, db_path, source_ref)
            return (
                ReportExtraction(
                    exam_info=ExamInfo(study_description="Chest XR"),
                    findings=[
                        ExtractedFinding(
                            finding_name="pneumonia",
                            presence="present",
                            report_text="Pneumonia seen.",
                        )
                    ],
                ),
                None,
                StorageMetadata(
                    db_path=str(db_path),
                    report_id="r-table",
                    report_seen_before=False,
                    extraction_id="e-table",
                    model_name="openai:gpt-5-mini",
                    reasoning_effort=None,
                    extracted_at="2026-02-11T00:00:00+00:00",
                ),
            )

        monkeypatch.setattr(
            "finding_extractor.cli.run_extraction_pipeline", fake_run_extraction_pipeline
        )
        monkeypatch.setattr(
            "finding_extractor.store.ExtractionStore.check_migration_current",
            lambda self: _async_none(),
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("Pneumonia seen.")
            result = runner.invoke(main, [str(report_path), "--store", "--format", "table"])

            assert result.exit_code == 0
            assert "PERSISTENCE:" in result.output
            assert "Report ID:" in result.output
            assert "Extraction ID:" in result.output

    def test_cli_emits_progress_on_stderr(self, monkeypatch):
        """CLI should emit progress messages to stderr during extraction."""

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
            status_callback=None,
        ):
            _ = (report_text, exam_type, model, reasoning, validate, store, db_path, source_ref)
            if status_callback is not None:
                await status_callback("Validating model configuration...")
                await status_callback("Calling model...")
                await status_callback("Model call complete, processing results")
                await status_callback("Done.")
            return (
                ReportExtraction(
                    exam_info=ExamInfo(study_description="Chest XR"),
                    findings=[
                        ExtractedFinding(
                            finding_name="pleural effusion",
                            presence="absent",
                            report_text="No pleural effusion.",
                        )
                    ],
                ),
                None,
                None,
            )

        monkeypatch.setattr(
            "finding_extractor.cli.run_extraction_pipeline", fake_run_extraction_pipeline
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("No pleural effusion.")

            result = runner.invoke(main, [str(report_path), "--format", "json"])
            assert result.exit_code == 0
            assert "Validating model configuration..." in result.stderr
            assert "Calling model..." in result.stderr
            assert "Model call complete, processing results" in result.stderr
            assert "Done." in result.stderr

    def test_cli_rejects_incompatible_reasoning(self):
        """CLI should fail when reasoning level is incompatible with model provider."""
        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("No pleural effusion.")

            result = runner.invoke(
                main, [str(report_path), "--model", "ollama:llama4", "--reasoning", "high"]
            )
            assert result.exit_code == 1
            assert "not supported by ollama" in result.output

    def test_cli_store_migration_preflight_rejects_outdated_db(self, monkeypatch):
        """When --store targets a DB at wrong revision, CLI should fail with migration hint."""

        async def fake_check_migration(self) -> str | None:
            return "Database is at revision 17f8ebc6c608, expected a3f1c8b2d4e6. Run 'task db:migrate' to upgrade."

        monkeypatch.setattr(
            "finding_extractor.store.ExtractionStore.check_migration_current",
            fake_check_migration,
        )

        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("No pleural effusion.")
            db_path = Path("outdated.sqlite3")

            result = runner.invoke(
                main,
                [str(report_path), "--store", "--db-path", str(db_path)],
            )
            assert result.exit_code != 0
            assert "expected a3f1c8b2d4e6" in result.output
            assert "task db:migrate" in result.output

    def test_cli_store_fresh_db_fails_preflight_without_creating_tables(self):
        """Fresh DB + --store should fail preflight and leave DB without app tables."""
        import sqlite3

        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("No pleural effusion.")
            db_path = Path("fresh.sqlite3")

            result = runner.invoke(
                main,
                [str(report_path), "--store", "--db-path", str(db_path)],
            )
            assert result.exit_code != 0
            assert "task db:migrate" in (result.output + result.stderr)

            # DB file may or may not exist (engine may create it),
            # but app tables must not have been created.
            if db_path.exists():
                conn = sqlite3.connect(str(db_path))
                tables = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                }
                conn.close()
                for app_table in ("reports", "extractions", "corrections", "jobs"):
                    assert app_table not in tables, (
                        f"Table '{app_table}' should not exist after preflight failure"
                    )
