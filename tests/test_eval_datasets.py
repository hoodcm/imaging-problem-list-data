"""Tests for eval dataset import and save logic."""

from __future__ import annotations

import json
from pathlib import Path

from finding_extractor.eval.datasets import (
    import_baseline_cases,
    load_dataset,
    save_dataset,
)
from finding_extractor.eval.models import EvalInput, EvalMetadata
from finding_extractor.models import ExamInfo, ReportExtraction


def _make_extraction_json(
    *,
    modality: str = "CT",
    body_part: str = "abdomen",
    model: str | None = None,
    include_validation: bool = False,
    include_storage: bool = False,
) -> dict:
    """Build a minimal valid ReportExtraction JSON dict for testing."""
    payload: dict = {
        "exam_info": {
            "study_description": f"{modality} {body_part}",
            "modality": modality,
            "body_part": body_part,
        },
        "findings": [
            {
                "finding_name": "test finding",
                "presence": "present",
                "location": {"body_region": body_part},
                "attributes": [],
                "report_text": "test finding text",
            }
        ],
        "non_finding_text": [],
    }
    if include_validation:
        payload["_validation"] = {"is_valid": True, "verbatim_errors": [], "coverage_warnings": []}
    if include_storage:
        storage: dict = {"db_path": "/tmp/test.db", "report_id": "r1", "extraction_id": "e1"}
        if model:
            storage["model"] = model
        payload["_storage"] = storage
    return payload


def _write_pair(
    tmp_path: Path,
    stem: str,
    report_text: str,
    extraction_json: dict,
    report_ext: str = ".txt",
    output_suffix: str = ".extracted.json",
) -> tuple[Path, Path]:
    """Write a report + extraction file pair to tmp_path."""
    report_path = tmp_path / f"{stem}{report_ext}"
    report_path.write_text(report_text, encoding="utf-8")
    extraction_path = tmp_path / f"{stem}{output_suffix}"
    extraction_path.write_text(
        json.dumps(extraction_json, indent=2), encoding="utf-8"
    )
    return report_path, extraction_path


class TestImportBaselineCases:
    def test_basic_import(self, tmp_path: Path):
        _write_pair(tmp_path, "ct_test", "Report text here", _make_extraction_json())
        cases = import_baseline_cases(tmp_path)
        assert len(cases) == 1
        assert cases[0].name == "ct_test"
        assert cases[0].inputs.report_text == "Report text here"
        assert cases[0].expected_output is not None
        assert len(cases[0].expected_output.findings) == 1
        assert cases[0].metadata is not None
        assert cases[0].metadata.modality == "CT"
        assert cases[0].metadata.body_region == "abdomen"

    def test_strips_validation_and_storage_keys(self, tmp_path: Path):
        extraction = _make_extraction_json(include_validation=True, include_storage=True)
        _write_pair(tmp_path, "with_extras", "Report", extraction)
        cases = import_baseline_cases(tmp_path)
        assert len(cases) == 1
        # The extraction should parse successfully without _validation/_storage
        assert cases[0].expected_output is not None

    def test_infers_metadata_from_exam_info(self, tmp_path: Path):
        extraction = _make_extraction_json(modality="MR", body_part="head")
        _write_pair(tmp_path, "mr_brain", "MR report", extraction)
        cases = import_baseline_cases(tmp_path)
        assert len(cases) == 1
        assert cases[0].metadata is not None
        assert cases[0].metadata.modality == "MR"
        assert cases[0].metadata.body_region == "head"

    def test_generates_case_name_from_filename(self, tmp_path: Path):
        _write_pair(tmp_path, "ct_abdomen_20210826", "Report", _make_extraction_json())
        cases = import_baseline_cases(tmp_path)
        assert cases[0].name == "ct_abdomen_20210826"

    def test_skips_missing_extraction_file(self, tmp_path: Path):
        # Only write the report, no extraction
        (tmp_path / "orphan.txt").write_text("Report with no extraction")
        cases = import_baseline_cases(tmp_path)
        assert len(cases) == 0

    def test_skips_parse_errors(self, tmp_path: Path):
        (tmp_path / "bad.txt").write_text("Report")
        (tmp_path / "bad.extracted.json").write_text("not valid json{{{")
        cases = import_baseline_cases(tmp_path)
        assert len(cases) == 0

    def test_skips_validation_errors(self, tmp_path: Path):
        (tmp_path / "invalid.txt").write_text("Report")
        # Write JSON that's valid JSON but not a valid ReportExtraction
        (tmp_path / "invalid.extracted.json").write_text(
            json.dumps({"not_a_valid": "extraction"})
        )
        cases = import_baseline_cases(tmp_path)
        assert len(cases) == 0

    def test_custom_glob(self, tmp_path: Path):
        extraction = _make_extraction_json()
        _write_pair(tmp_path, "report1", "Report", extraction, report_ext=".md")
        # Also add a .txt that won't match
        (tmp_path / "ignored.txt").write_text("Ignored")
        cases = import_baseline_cases(tmp_path, glob="*.md")
        assert len(cases) == 1
        assert cases[0].name == "report1"

    def test_custom_output_suffix(self, tmp_path: Path):
        extraction = _make_extraction_json()
        _write_pair(
            tmp_path, "report1", "Report", extraction, output_suffix=".result.json"
        )
        cases = import_baseline_cases(tmp_path, output_suffix=".result.json")
        assert len(cases) == 1

    def test_source_label(self, tmp_path: Path):
        _write_pair(tmp_path, "test", "Report", _make_extraction_json())
        cases = import_baseline_cases(tmp_path, source_label="my_source")
        assert cases[0].metadata is not None
        assert cases[0].metadata.source_file == "my_source"

    def test_default_source_label_is_dirname(self, tmp_path: Path):
        _write_pair(tmp_path, "test", "Report", _make_extraction_json())
        cases = import_baseline_cases(tmp_path)
        assert cases[0].metadata is not None
        assert cases[0].metadata.source_file == tmp_path.name

    def test_model_filter(self, tmp_path: Path):
        ext_a = _make_extraction_json(include_storage=True, model="openai:gpt-5-mini")
        ext_b = _make_extraction_json(include_storage=True, model="anthropic:claude-sonnet-4-5")
        _write_pair(tmp_path, "report_a", "Report A", ext_a)
        _write_pair(tmp_path, "report_b", "Report B", ext_b)
        cases = import_baseline_cases(tmp_path, model_filter="openai:gpt-5-mini")
        assert len(cases) == 1
        assert cases[0].name == "report_a"

    def test_multiple_files_sorted(self, tmp_path: Path):
        for name in ["zebra", "alpha", "middle"]:
            _write_pair(tmp_path, name, f"Report {name}", _make_extraction_json())
        cases = import_baseline_cases(tmp_path)
        assert len(cases) == 3
        assert [c.name for c in cases] == ["alpha", "middle", "zebra"]

    def test_empty_directory(self, tmp_path: Path):
        cases = import_baseline_cases(tmp_path)
        assert cases == []


class TestSaveDataset:
    def test_save_by_name(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "finding_extractor.eval.datasets.get_settings",
            lambda: type("S", (), {"eval_dataset_dir": tmp_path})(),
        )
        from pydantic_evals import Case, Dataset

        dataset = Dataset[EvalInput, ReportExtraction, EvalMetadata](
            cases=[
                Case(
                    name="test",
                    inputs=EvalInput(report_text="test"),
                    expected_output=ReportExtraction(
                        exam_info=ExamInfo(study_description="test"),
                        findings=[],
                        non_finding_text=[],
                    ),
                    metadata=EvalMetadata(),
                )
            ]
        )
        path = save_dataset(dataset, "mytest")
        assert path == tmp_path / "mytest.yaml"
        assert path.exists()

    def test_save_by_path(self, tmp_path: Path):
        from pydantic_evals import Case, Dataset

        out = tmp_path / "custom.yaml"
        dataset = Dataset[EvalInput, ReportExtraction, EvalMetadata](
            cases=[
                Case(
                    name="test",
                    inputs=EvalInput(report_text="test"),
                    expected_output=ReportExtraction(
                        exam_info=ExamInfo(study_description="test"),
                        findings=[],
                        non_finding_text=[],
                    ),
                    metadata=EvalMetadata(),
                )
            ]
        )
        path = save_dataset(dataset, str(out))
        assert path == out
        assert path.exists()

    def test_round_trip(self, tmp_path: Path, monkeypatch):
        monkeypatch.setattr(
            "finding_extractor.eval.datasets.get_settings",
            lambda: type("S", (), {"eval_dataset_dir": tmp_path})(),
        )
        from pydantic_evals import Case, Dataset

        original = Dataset[EvalInput, ReportExtraction, EvalMetadata](
            cases=[
                Case(
                    name="rt_test",
                    inputs=EvalInput(report_text="round trip text"),
                    expected_output=ReportExtraction(
                        exam_info=ExamInfo(study_description="RT test"),
                        findings=[],
                        non_finding_text=[],
                    ),
                    metadata=EvalMetadata(modality="CT"),
                )
            ]
        )
        save_dataset(original, "roundtrip")
        loaded = load_dataset(str(tmp_path / "roundtrip.yaml"))
        assert len(loaded.cases) == 1
        assert loaded.cases[0].name == "rt_test"
        assert loaded.cases[0].inputs.report_text == "round trip text"
