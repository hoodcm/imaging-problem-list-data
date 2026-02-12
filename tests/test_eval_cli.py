"""Tests for the evaluation CLI."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from finding_extractor.eval_cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def _mock_logging(monkeypatch):
    monkeypatch.setattr(
        "finding_extractor.eval_cli.configure_logfire",
        lambda runtime, **kw: False,
    )
    monkeypatch.setattr(
        "finding_extractor.eval_cli.setup_logging",
        lambda settings, *, include_logfire_processor: None,
    )


class TestEvalCli:
    def test_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Evaluation harness" in result.output

    def test_run_help(self, runner: CliRunner):
        result = runner.invoke(cli, ["run", "--help"])
        assert result.exit_code == 0
        assert "--dataset" in result.output
        assert "--model" in result.output
        assert "--threshold-f1" in result.output
        assert "--threshold-presence" in result.output
        assert "--threshold-verbatim" in result.output

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_run_defaults(self, mock_run: MagicMock, runner: CliRunner, tmp_path: Path):
        mock_run.return_value = ({"finding_f1": 0.8}, 0)
        result = runner.invoke(
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

    @patch("finding_extractor.eval_cli._run_eval_sync")
    def test_run_with_model(self, mock_run: MagicMock, runner: CliRunner, tmp_path: Path):
        mock_run.return_value = ({"finding_f1": 0.9}, 0)
        result = runner.invoke(
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
    def test_run_with_thresholds(self, mock_run: MagicMock, runner: CliRunner, tmp_path: Path):
        mock_run.return_value = ({"finding_f1": 0.8, "presence_accuracy": 0.9}, 0)
        result = runner.invoke(
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
        self, mock_run: MagicMock, runner: CliRunner, tmp_path: Path
    ):
        mock_run.return_value = ({"verbatim_pass": 1.0}, 0)
        result = runner.invoke(
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
        self, mock_run: MagicMock, runner: CliRunner, tmp_path: Path
    ):
        mock_run.return_value = ({"finding_f1": 0.3}, 1)
        result = runner.invoke(
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

    def test_invalid_model_rejected(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
            cli,
            ["run", "--dataset", "smoke", "--model", "badmodel", "--run-dir", str(tmp_path)],
        )
        assert result.exit_code != 0

    def test_invalid_reasoning_for_model(self, runner: CliRunner, tmp_path: Path):
        result = runner.invoke(
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
