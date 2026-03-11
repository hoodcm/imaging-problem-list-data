"""Data models for the evaluation harness."""

from __future__ import annotations

from dataclasses import dataclass, field

from finding_extractor.core.base_model import StrictBaseModel


class EvalInput(StrictBaseModel):
    """Input for a single eval case: the report text and optional exam description."""

    report_text: str
    study_description: str | None = None


class EvalMetadata(StrictBaseModel):
    """Metadata for a single eval case, used for filtering and reporting."""

    source_file: str | None = None
    modality: str | None = None
    body_region: str | None = None
    difficulty: str | None = None
    tags: list[str] = []


@dataclass(frozen=True)
class EvalRunConfig:
    """Configuration for an evaluation run."""

    run_id: str
    dataset_path: str
    model: str
    reasoning: str | None
    workers: int
    timeout_seconds: int
    run_dir: str
    retries: int = 0
    thresholds: dict[str, float] = field(default_factory=dict)
