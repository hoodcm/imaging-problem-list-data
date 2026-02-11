"""Tests for the finding extractor CLI."""

import json
from pathlib import Path

from click.testing import CliRunner

from finding_extractor.cli import format_json_output, format_table_output, main
from finding_extractor.extraction_pipeline import StorageMetadata
from finding_extractor.models import (
    ExamInfo,
    ExtractedFinding,
    FindingAttribute,
    FindingLocation,
    ReportExtraction,
    ValidationResult,
)


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

            result = runner.invoke(main, [str(report_path), "--model", "google-vertex:gemini-3-pro"])
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

        monkeypatch.setattr("finding_extractor.cli.run_extraction_pipeline", fake_run_extraction_pipeline)

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
            payload = json.loads(result.output)
            assert "_storage" in payload
            assert payload["_storage"]["db_path"] == str(db_path)
            assert payload["_storage"]["report_seen_before"] is False
            assert payload["_storage"]["model_name"] == "openai:gpt-5-mini"
            assert payload["_storage"]["report_id"]
            assert payload["_storage"]["extraction_id"]
            assert payload["_storage"]["extracted_at"]

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

        monkeypatch.setattr("finding_extractor.cli.run_extraction_pipeline", fake_run_extraction_pipeline)

        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("Cardiomediastinal silhouette is normal.")

            result = runner.invoke(main, [str(report_path), "--format", "json"])
            assert result.exit_code == 0
            payload = json.loads(result.output)
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

        monkeypatch.setattr("finding_extractor.cli.run_extraction_pipeline", fake_run_extraction_pipeline)

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

            first_payload = json.loads(first.output)
            second_payload = json.loads(second.output)
            assert first_payload["_storage"]["report_seen_before"] is False
            assert second_payload["_storage"]["report_seen_before"] is True
            assert first_payload["_storage"]["report_id"] == second_payload["_storage"]["report_id"]
            assert first_payload["_storage"]["extraction_id"] != second_payload["_storage"]["extraction_id"]

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

        monkeypatch.setattr("finding_extractor.cli.run_extraction_pipeline", fake_run_extraction_pipeline)

        runner = CliRunner()
        with runner.isolated_filesystem():
            report_path = Path("report.md")
            report_path.write_text("Pneumonia seen.")
            result = runner.invoke(main, [str(report_path), "--store", "--format", "table"])

            assert result.exit_code == 0
            assert "PERSISTENCE:" in result.output
            assert "Report ID:" in result.output
            assert "Extraction ID:" in result.output
