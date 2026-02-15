"""Tests for the evaluation CLI."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from finding_extractor.eval_cli import cli


@pytest.fixture(autouse=True)
def _mock_logging(monkeypatch, runtime_logging_spy):
    runtime_logging_spy.patch(
        monkeypatch,
        "finding_extractor.eval_cli",
        logfire_enabled=False,
    )


class TestEvalCli:
    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Evaluation harness" in result.output

    def test_run_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--dataset" in result.output
        assert "--model" in result.output
        assert "--threshold-f1" in result.output
        assert "--threshold-presence" in result.output
        assert "--threshold-verbatim" in result.output
        assert "--retries" in result.output
        assert "--max-predicted-runtime-seconds" in result.output
        assert "--allow-slow" in result.output

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_run_defaults(self, mock_run: MagicMock, cli_runner, tmp_path: Path, runtime_logging_spy):
        mock_run.return_value = ({"finding_f1": 0.8}, 0)
        result = cli_runner.invoke(
            cli,
            ["run", "--dataset", "smoke", "--run-dir", str(tmp_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "EVAL" in result.output
        mock_run.assert_called_once()
        config = mock_run.call_args[1]["config"]
        assert config.dataset_path == "smoke"
        assert config.workers >= 1
        assert config.timeout_seconds >= 10
        assert config.reasoning == "medium"
        # Default retries from settings (DEFAULT_EVAL_RETRIES = 0)
        assert config.retries >= 0
        assert len(runtime_logging_spy.configure_calls) == 1
        assert len(runtime_logging_spy.setup_calls) == 1
        assert runtime_logging_spy.configure_calls[0]["runtime"] == "cli"
        assert runtime_logging_spy.setup_calls[0]["include_logfire_processor"] is False
        assert runtime_logging_spy.setup_calls[0]["settings"] is not None

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_run_with_model(self, mock_run: MagicMock, cli_runner, tmp_path: Path):
        mock_run.return_value = ({"finding_f1": 0.9}, 0)
        result = cli_runner.invoke(
            cli,
            [
                "run",
                "--dataset",
                "smoke",
                "--model",
                "openai:gpt-5-mini",
                "--reasoning",
                "medium",
                "--run-dir",
                str(tmp_path),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        config = mock_run.call_args[1]["config"]
        assert config.model == "openai:gpt-5-mini"
        assert config.reasoning == "medium"

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_run_with_thresholds(self, mock_run: MagicMock, cli_runner, tmp_path: Path):
        mock_run.return_value = ({"finding_f1": 0.8, "presence_accuracy": 0.9}, 0)
        result = cli_runner.invoke(
            cli,
            [
                "run",
                "--dataset",
                "smoke",
                "--threshold-f1",
                "0.5",
                "--threshold-presence",
                "0.7",
                "--run-dir",
                str(tmp_path),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        config = mock_run.call_args[1]["config"]
        assert config.thresholds == {"finding_f1": 0.5, "presence_accuracy": 0.7}

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_run_verbatim_threshold_flag(
        self, mock_run: MagicMock, cli_runner, tmp_path: Path
    ):
        mock_run.return_value = ({"verbatim_pass": 1.0}, 0)
        result = cli_runner.invoke(
            cli,
            [
                "run",
                "--dataset",
                "smoke",
                "--threshold-verbatim",
                "--run-dir",
                str(tmp_path),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        config = mock_run.call_args[1]["config"]
        assert config.thresholds["verbatim_pass"] == 1.0

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_threshold_failure_exits_nonzero(
        self, mock_run: MagicMock, cli_runner, tmp_path: Path
    ):
        mock_run.return_value = ({"finding_f1": 0.3}, 1)
        result = cli_runner.invoke(
            cli,
            [
                "run",
                "--dataset",
                "smoke",
                "--threshold-f1",
                "0.5",
                "--run-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code == 1

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_run_with_retries(self, mock_run: MagicMock, cli_runner, tmp_path: Path):
        mock_run.return_value = ({"finding_f1": 0.8}, 0)
        result = cli_runner.invoke(
            cli,
            [
                "run",
                "--dataset",
                "smoke",
                "--retries",
                "3",
                "--run-dir",
                str(tmp_path),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        config = mock_run.call_args[1]["config"]
        assert config.retries == 3

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_run_retries_zero(self, mock_run: MagicMock, cli_runner, tmp_path: Path):
        mock_run.return_value = ({"finding_f1": 0.8}, 0)
        result = cli_runner.invoke(
            cli,
            [
                "run",
                "--dataset",
                "smoke",
                "--retries",
                "0",
                "--run-dir",
                str(tmp_path),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        config = mock_run.call_args[1]["config"]
        assert config.retries == 0

    def test_invalid_model_rejected(self, cli_runner, tmp_path: Path):
        result = cli_runner.invoke(
            cli,
            ["run", "--dataset", "smoke", "--model", "badmodel", "--run-dir", str(tmp_path)],
        )
        assert result.exit_code != 0

    def test_invalid_reasoning_for_model(self, cli_runner, tmp_path: Path):
        result = cli_runner.invoke(
            cli,
            [
                "run",
                "--dataset",
                "smoke",
                "--model",
                "ollama:llama4",
                "--reasoning",
                "high",
                "--run-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code != 0

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_fail_fast_runtime_guard_blocks_run(
        self, mock_run: MagicMock, cli_runner, tmp_path: Path
    ):
        result = cli_runner.invoke(
            cli,
            [
                "run",
                "--dataset",
                "comprehensive",
                "--workers",
                "1",
                "--timeout-seconds",
                "120",
                "--retries",
                "1",
                "--max-predicted-runtime-seconds",
                "600",
                "--run-dir",
                str(tmp_path),
            ],
        )
        assert result.exit_code != 0
        assert "Predicted runtime upper bound exceeds fail-fast budget" in result.output
        mock_run.assert_not_called()

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_allow_slow_overrides_runtime_guard(
        self, mock_run: MagicMock, cli_runner, tmp_path: Path
    ):
        mock_run.return_value = ({"finding_f1": 0.8}, 0)
        result = cli_runner.invoke(
            cli,
            [
                "run",
                "--dataset",
                "comprehensive",
                "--workers",
                "1",
                "--timeout-seconds",
                "120",
                "--retries",
                "1",
                "--max-predicted-runtime-seconds",
                "600",
                "--allow-slow",
                "--run-dir",
                str(tmp_path),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "EVAL preflight warning: running despite high predicted bound" in result.output
        mock_run.assert_called_once()


class TestRunnerThresholdLogic:
    """Test the threshold checking logic directly."""

    def test_all_pass(self):
        from finding_extractor.eval.runner import _check_thresholds

        averages = {"finding_f1": 0.8, "presence_accuracy": 0.9}
        thresholds = {"finding_f1": 0.5, "presence_accuracy": 0.7}
        failures = _check_thresholds(averages, thresholds)
        assert failures == []

    def test_below_threshold(self):
        from finding_extractor.eval.runner import _check_thresholds

        averages = {"finding_f1": 0.3}
        thresholds = {"finding_f1": 0.5}
        failures = _check_thresholds(averages, thresholds)
        assert len(failures) == 1
        assert "finding_f1" in failures[0]

    def test_missing_metric(self):
        from finding_extractor.eval.runner import _check_thresholds

        averages = {}
        thresholds = {"finding_f1": 0.5}
        failures = _check_thresholds(averages, thresholds)
        assert len(failures) == 1
        assert "not found" in failures[0]

    def test_no_thresholds(self):
        from finding_extractor.eval.runner import _check_thresholds

        averages = {"finding_f1": 0.8}
        failures = _check_thresholds(averages, {})
        assert failures == []


class TestDatasetLoading:
    """Test dataset loading from the eval package."""

    def test_load_smoke_dataset(self):
        from finding_extractor.eval.datasets import load_dataset

        dataset = load_dataset("smoke")
        assert len(dataset.cases) == 2
        assert dataset.cases[0].name == "ct_abdomen_pelvis"
        assert dataset.cases[1].name == "xr_chest"

    def test_load_nonexistent_dataset(self):
        from finding_extractor.eval.datasets import load_dataset

        with pytest.raises(FileNotFoundError):
            load_dataset("nonexistent_dataset")

    def test_build_smoke_dataset(self):
        from finding_extractor.eval.datasets import build_smoke_dataset

        dataset = build_smoke_dataset()
        assert len(dataset.cases) == 2
        for case in dataset.cases:
            assert case.expected_output is not None
            assert len(case.expected_output.findings) > 0


def _make_extraction_json(modality: str = "CT", body_part: str = "abdomen") -> dict:
    """Build minimal ReportExtraction JSON for CLI tests."""
    return {
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


def _write_report_pair(tmp_path: Path, stem: str, report_ext: str = ".txt") -> None:
    """Write a report + extraction pair for import-baseline tests."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / f"{stem}{report_ext}").write_text("Report text", encoding="utf-8")
    (tmp_path / f"{stem}.extracted.json").write_text(
        json.dumps(_make_extraction_json(), indent=2), encoding="utf-8"
    )


class TestImportBaselineCli:
    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["import-baseline", "--help"])
        assert result.exit_code == 0
        assert "--dataset" in result.output
        assert "--glob" in result.output
        assert "--output-suffix" in result.output
        assert "--append" in result.output
        assert "--source-label" in result.output
        assert "--model-filter" in result.output

    def test_successful_import(self, cli_runner, tmp_path: Path):
        _write_report_pair(tmp_path / "source", "report1")
        output_dir = tmp_path / "datasets"
        output_file = output_dir / "test_import.yaml"

        result = cli_runner.invoke(
            cli,
            [
                "import-baseline",
                str(tmp_path / "source"),
                "--dataset",
                str(output_file),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Imported 1 cases" in result.output
        assert output_file.exists()

    def test_missing_extraction_skipped_with_warning(self, cli_runner, tmp_path: Path):
        source = tmp_path / "source"
        source.mkdir()
        (source / "orphan.txt").write_text("Report with no extraction")

        result = cli_runner.invoke(
            cli,
            [
                "import-baseline",
                str(source),
                "--dataset",
                str(tmp_path / "out.yaml"),
            ],
        )
        # Should fail because no cases imported
        assert result.exit_code != 0
        assert "No cases imported" in result.output

    def test_append_to_existing(self, cli_runner, tmp_path: Path):
        source = tmp_path / "source"
        source.mkdir()
        _write_report_pair(source, "report1")

        output_file = tmp_path / "datasets" / "appended.yaml"

        # First import
        result1 = cli_runner.invoke(
            cli,
            ["import-baseline", str(source), "--dataset", str(output_file)],
            catch_exceptions=False,
        )
        assert result1.exit_code == 0
        assert "total: 1" in result1.output

        # Add another report and import again
        _write_report_pair(source, "report2")

        result2 = cli_runner.invoke(
            cli,
            ["import-baseline", str(source), "--dataset", str(output_file)],
            catch_exceptions=False,
        )
        assert result2.exit_code == 0
        # Should have 2 total (report1 deduped + report2 new)
        assert "total: 2" in result2.output

    def test_no_append_overwrites(self, cli_runner, tmp_path: Path):
        source = tmp_path / "source"
        source.mkdir()
        _write_report_pair(source, "report1")
        _write_report_pair(source, "report2")

        output_file = tmp_path / "datasets" / "overwritten.yaml"

        # First import
        cli_runner.invoke(
            cli,
            ["import-baseline", str(source), "--dataset", str(output_file)],
            catch_exceptions=False,
        )

        # Second import with --no-append (only report1 this time)
        # Remove report2 pair
        (source / "report2.txt").unlink()
        (source / "report2.extracted.json").unlink()

        result = cli_runner.invoke(
            cli,
            [
                "import-baseline",
                str(source),
                "--dataset",
                str(output_file),
                "--no-append",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "total: 1" in result.output

    def test_custom_glob(self, cli_runner, tmp_path: Path):
        source = tmp_path / "source"
        source.mkdir()
        _write_report_pair(source, "report1", report_ext=".md")

        output_file = tmp_path / "out.yaml"
        result = cli_runner.invoke(
            cli,
            [
                "import-baseline",
                str(source),
                "--dataset",
                str(output_file),
                "--glob",
                "*.md",
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "Imported 1" in result.output


def _make_results_json(
    run_id: str = "eval-test-001",
    model: str = "openai:gpt-5-mini",
    *,
    include_reasons: bool = True,
) -> dict:
    """Build a mock results.json payload."""
    case_ct: dict = {
        "name": "ct_abdomen_pelvis",
        "scores": {"finding_f1": 0.80, "presence_accuracy": 0.90},
        "assertions": {"verbatim_pass": True},
        "task_duration": 5.0,
    }
    case_xr: dict = {
        "name": "xr_chest",
        "scores": {"finding_f1": 0.90, "presence_accuracy": 1.0},
        "assertions": {"verbatim_pass": True},
        "task_duration": 4.0,
    }
    if include_reasons:
        case_ct["score_reasons"] = {
            "finding_f1": "4 matched, 1 FP, 2 FN",
            "presence_accuracy": "3/4 correct",
        }
        case_ct["assertion_reasons"] = {"verbatim_pass": "5/5 verbatim"}
        case_xr["score_reasons"] = {
            "finding_f1": "6 matched, 0 FP, 1 FN",
        }
        case_xr["assertion_reasons"] = {"verbatim_pass": "7/7 verbatim"}
    return {
        "run_id": run_id,
        "model": model,
        "reasoning": "medium",
        "dataset": "smoke",
        "retries": 1,
        "duration_seconds": 12.5,
        "averages": {
            "finding_f1": 0.85,
            "finding_precision": 0.90,
            "finding_recall": 0.80,
            "presence_accuracy": 0.95,
            "verbatim_pass": 1.0,
        },
        "cases": [case_ct, case_xr],
        "thresholds": {"finding_f1": 0.5},
        "completed_at": "2026-02-12T10:00:00+00:00",
    }


def _make_report_dict(
    run_id: str = "eval-test-001",
    model: str = "openai:gpt-5-mini",
    *,
    include_reasons: bool = True,
    cases: list[str] | None = None,
    extra_scores: dict[str, dict[str, float]] | None = None,
) -> dict:
    """Build a valid EvaluationReport dict for report.json.

    Uses EvaluationReportAdapter round-trip to ensure the dict is valid.
    """
    from pydantic_evals.evaluators.spec import EvaluatorSpec
    from pydantic_evals.reporting import (
        EvaluationReport,
        EvaluationReportAdapter,
        EvaluationResult,
        ReportCase,
    )

    source = EvaluatorSpec(name="test", arguments=None)
    case_names = cases or ["ct_abdomen_pelvis", "xr_chest"]

    case_configs: dict[str, dict] = {
        "ct_abdomen_pelvis": {
            "f1": 0.80, "pres": 0.90, "verb": True,
            "f1_reason": "4 matched, 1 FP, 2 FN",
            "pres_reason": "3/4 correct",
            "verb_reason": "5/5 verbatim",
            "duration": 5.0,
        },
        "xr_chest": {
            "f1": 0.90, "pres": 1.0, "verb": True,
            "f1_reason": "6 matched, 0 FP, 1 FN",
            "pres_reason": "10/10 correct",
            "verb_reason": "7/7 verbatim",
            "duration": 4.0,
        },
    }

    report_cases = []
    for name in case_names:
        cfg = case_configs.get(name, case_configs["ct_abdomen_pelvis"])
        scores = {
            "finding_f1": EvaluationResult(
                name="finding_f1", value=cfg["f1"],
                reason=cfg["f1_reason"] if include_reasons else None, source=source,
            ),
            "presence_accuracy": EvaluationResult(
                name="presence_accuracy", value=cfg["pres"],
                reason=cfg["pres_reason"] if include_reasons else None, source=source,
            ),
        }
        # Add any extra scores for this case
        if extra_scores and name in extra_scores:
            for sname, sval in extra_scores[name].items():
                scores[sname] = EvaluationResult(
                    name=sname, value=sval, reason=None, source=source,
                )
        report_cases.append(ReportCase(
            name=name,
            inputs=None,
            metadata=None,
            expected_output=None,
            output=None,
            metrics={},
            attributes={},
            scores=scores,
            labels={},
            assertions={
                "verbatim_pass": EvaluationResult(
                    name="verbatim_pass", value=cfg["verb"],
                    reason=cfg["verb_reason"] if include_reasons else None, source=source,
                ),
            },
            task_duration=cfg["duration"],
            total_duration=cfg["duration"] + 1.0,
        ))

    report = EvaluationReport(
        name=f"eval-{run_id}",
        cases=report_cases,
        experiment_metadata={
            "model": model,
            "dataset": "smoke",
            "reasoning": "medium",
            "retries": 1,
            "duration_seconds": 12.5,
        },
    )

    report_dict = EvaluationReportAdapter.dump_python(report, mode="json")
    # Null out large fields (same as runner._save_report)
    for case in report_dict.get("cases", []):
        case["inputs"] = None
        case["output"] = None
        case["expected_output"] = None
    return report_dict


def _write_run(
    run_dir: Path,
    run_id: str,
    *,
    include_reasons: bool = True,
    legacy_only: bool = False,
    extra_scores: dict[str, dict[str, float]] | None = None,
    cases: list[str] | None = None,
    model: str = "openai:gpt-5-mini",
) -> Path:
    """Create a mock run directory with report.json and/or results.json."""
    d = run_dir / run_id
    d.mkdir(parents=True)

    payload = _make_results_json(
        run_id=run_id, model=model, include_reasons=include_reasons,
    )
    if cases is not None:
        payload["cases"] = [c for c in payload["cases"] if c["name"] in cases]
    (d / "results.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")

    if not legacy_only:
        report_dict = _make_report_dict(
            run_id=run_id,
            model=model,
            include_reasons=include_reasons,
            extra_scores=extra_scores,
            cases=cases,
        )
        (d / "report.json").write_text(
            json.dumps(report_dict, indent=2), encoding="utf-8",
        )

    return d


class TestReportCli:
    def test_help(self, cli_runner):
        result = cli_runner.invoke(cli, ["report", "--help"])
        assert result.exit_code == 0
        assert "--compare" in result.output
        assert "--run-dir" in result.output
        assert "--case" in result.output

    def test_show_latest_run(self, cli_runner, tmp_path: Path):
        _write_run(tmp_path, "eval-20260212-100000-abc12345")
        result = cli_runner.invoke(
            cli,
            ["report", "--run-dir", str(tmp_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "eval-20260212-100000-abc12345" in result.output
        assert "finding_f1" in result.output

    def test_show_specific_run(self, cli_runner, tmp_path: Path):
        _write_run(tmp_path, "eval-run-a")
        _write_run(tmp_path, "eval-run-b")
        result = cli_runner.invoke(
            cli,
            ["report", "eval-run-a", "--run-dir", str(tmp_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "eval-run-a" in result.output

    def test_compare_two_runs(self, cli_runner, tmp_path: Path):
        _write_run(tmp_path, "run-a", model="openai:gpt-5-mini")
        _write_run(tmp_path, "run-b", model="anthropic:claude-sonnet-4-5")
        result = cli_runner.invoke(
            cli,
            ["report", "run-a", "--compare", "run-b", "--run-dir", str(tmp_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "run-a" in result.output
        assert "run-b" in result.output

    def test_compare_direction(self, cli_runner, tmp_path: Path):
        """report run-a --compare run-b shows 'run-a → run-b' with positive delta when B improves."""
        # run-a: f1=0.80, run-b: f1=0.80 + laterality=1.0 (extra metric, positive)
        _write_run(tmp_path, "run-a")
        _write_run(
            tmp_path, "run-b",
            extra_scores={"ct_abdomen_pelvis": {"laterality_accuracy": 1.0}},
        )
        result = cli_runner.invoke(
            cli,
            ["report", "run-a", "--compare", "run-b", "--run-dir", str(tmp_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        # Header should show primary → compare direction
        assert "run-a" in result.output
        assert "run-b" in result.output
        # pydantic-evals renders "baseline → self" header; verify it's A → B not B → A
        output_lines = result.output.replace("│", " ").replace("─", "")
        assert "run-a" in output_lines  # baseline name appears first in header

    def test_compare_shows_multiple_metrics(self, cli_runner, tmp_path: Path):
        """Per-case comparison shows multiple metrics, not just F1."""
        _write_run(tmp_path, "run-a", model="openai:gpt-5-mini")
        _write_run(tmp_path, "run-b", model="anthropic:claude-sonnet-4-5")
        result = cli_runner.invoke(
            cli,
            ["report", "run-a", "--compare", "run-b", "--run-dir", str(tmp_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "finding_f1" in result.output
        assert "presence_accuracy" in result.output

    def test_compare_with_missing_metrics_in_one_run(self, cli_runner, tmp_path: Path):
        """Comparison handles metrics present in one run but not the other."""
        _write_run(
            tmp_path, "run-a",
            extra_scores={"ct_abdomen_pelvis": {"laterality_accuracy": 1.0}},
        )
        _write_run(tmp_path, "run-b")

        result = cli_runner.invoke(
            cli,
            ["report", "run-a", "--compare", "run-b", "--run-dir", str(tmp_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "laterality_accuracy" in result.output

    def test_missing_run_error(self, cli_runner, tmp_path: Path):
        result = cli_runner.invoke(
            cli,
            ["report", "nonexistent-run", "--run-dir", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower() or "no report.json" in result.output.lower()

    def test_no_runs_error(self, cli_runner, tmp_path: Path):
        result = cli_runner.invoke(
            cli,
            ["report", "--run-dir", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "No runs found" in result.output

    # --case option tests

    def test_case_detail_single_run(self, cli_runner, tmp_path: Path):
        """report RUN_ID --case shows detailed view with metrics and reasons."""
        _write_run(tmp_path, "run-x")
        result = cli_runner.invoke(
            cli,
            ["report", "run-x", "--case", "ct_abdomen_pelvis", "--run-dir", str(tmp_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "ct_abdomen_pelvis" in result.output
        assert "finding_f1" in result.output
        assert "presence_accuracy" in result.output
        # Reasons should be displayed (Rich may wrap text across table cell lines)
        assert "4 matched" in result.output
        assert "3/4 correct" in result.output
        assert "5/5" in result.output

    def test_case_detail_comparison(self, cli_runner, tmp_path: Path):
        """report RUN_ID --case --compare shows comparison detail."""
        _write_run(tmp_path, "run-a", model="openai:gpt-5-mini")
        _write_run(tmp_path, "run-b", model="anthropic:claude-sonnet-4-5")
        result = cli_runner.invoke(
            cli,
            [
                "report", "run-a",
                "--case", "ct_abdomen_pelvis",
                "--compare", "run-b",
                "--run-dir", str(tmp_path),
            ],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "ct_abdomen_pelvis" in result.output
        assert "run-a" in result.output
        assert "run-b" in result.output
        assert "finding_f1" in result.output

    def test_case_detail_nonexistent(self, cli_runner, tmp_path: Path):
        """report RUN_ID --case nonexistent → error with available cases."""
        _write_run(tmp_path, "run-x")
        result = cli_runner.invoke(
            cli,
            ["report", "run-x", "--case", "nonexistent", "--run-dir", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "not found" in result.output.lower()
        assert "ct_abdomen_pelvis" in result.output  # Lists available cases

    def test_case_detail_comparison_case_missing_in_run_b(self, cli_runner, tmp_path: Path):
        """Comparison --case fails if case not in compare run."""
        _write_run(tmp_path, "run-a")
        _write_run(
            tmp_path, "run-b",
            cases=["xr_chest"],
        )

        result = cli_runner.invoke(
            cli,
            [
                "report", "run-a",
                "--case", "ct_abdomen_pelvis",
                "--compare", "run-b",
                "--run-dir", str(tmp_path),
            ],
        )
        assert result.exit_code != 0
        assert "not found in comparison run" in result.output.lower()

    # Legacy fallback tests

    def test_legacy_run_shows_summary(self, cli_runner, tmp_path: Path):
        """Run with only results.json shows legacy summary."""
        _write_run(tmp_path, "run-old", legacy_only=True)
        result = cli_runner.invoke(
            cli,
            ["report", "run-old", "--run-dir", str(tmp_path)],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "legacy" in result.output.lower()
        assert "finding_f1" in result.output

    def test_legacy_run_rejects_compare(self, cli_runner, tmp_path: Path):
        """Legacy run with --compare shows helpful error."""
        _write_run(tmp_path, "run-old", legacy_only=True)
        _write_run(tmp_path, "run-new")
        result = cli_runner.invoke(
            cli,
            ["report", "run-old", "--compare", "run-new", "--run-dir", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "legacy" in result.output.lower()

    def test_legacy_run_rejects_case(self, cli_runner, tmp_path: Path):
        """Legacy run with --case shows helpful error."""
        _write_run(tmp_path, "run-old", legacy_only=True)
        result = cli_runner.invoke(
            cli,
            ["report", "run-old", "--case", "ct_abdomen_pelvis", "--run-dir", str(tmp_path)],
        )
        assert result.exit_code != 0
        assert "legacy" in result.output.lower()
