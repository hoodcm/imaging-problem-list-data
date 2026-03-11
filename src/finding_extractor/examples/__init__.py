"""Few-shot examples for radiology report extraction.

Examples are stored as YAML files in this package directory.
"""

import importlib.resources
from typing import Any

import yaml

from finding_extractor.models import ExtractedReportFindings


def load_example(name: str) -> tuple[str, ExtractedReportFindings]:
    """Load a single named example from this package's YAML data files.

    Args:
        name: Example stem name (e.g. ``"ct_abdomen"``), without ``.yaml``.

    Returns:
        ``(report_text, ExtractedReportFindings)`` tuple.
    """
    examples_pkg = importlib.resources.files(__package__)
    raw = (examples_pkg / f"{name}.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    extraction = ExtractedReportFindings.model_validate(data["extraction"])
    return data["report_text"], extraction


def load_examples() -> list[tuple[str, ExtractedReportFindings]]:
    """Load all default examples from this package's YAML data files."""
    return [load_example("ct_abdomen"), load_example("xr_chest")]


def get_ct_abdomen_example() -> tuple[str, ExtractedReportFindings]:
    """Return (report_text, ExtractedReportFindings) for the CT abdomen example."""
    return load_example("ct_abdomen")


def get_xr_chest_example() -> tuple[str, ExtractedReportFindings]:
    """Return (report_text, ExtractedReportFindings) for the chest XR example."""
    return load_example("xr_chest")


def get_default_examples() -> list[tuple[str, ExtractedReportFindings]]:
    """Return the default set of few-shot examples."""
    return [get_ct_abdomen_example(), get_xr_chest_example()]


def load_chunk_examples() -> list[dict[str, Any]]:
    """Load chunk-level prompt examples from ``chunk_examples.yaml``.

    Returns:
        Parsed list of chunk example mappings under the top-level ``examples`` key.
    """
    examples_pkg = importlib.resources.files(__package__)
    raw = (examples_pkg / "chunk_examples.yaml").read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    examples = data.get("examples")
    if not isinstance(examples, list):
        raise ValueError("chunk_examples.yaml must contain a top-level 'examples' list")
    return [item for item in examples if isinstance(item, dict)]
