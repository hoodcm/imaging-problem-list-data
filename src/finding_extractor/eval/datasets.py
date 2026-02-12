"""Dataset loading and building helpers for the evaluation harness."""

from __future__ import annotations

from pathlib import Path

from pydantic_evals import Case, Dataset

from finding_extractor.config import get_settings
from finding_extractor.eval.models import EvalInput, EvalMetadata
from finding_extractor.models import ReportExtraction

# Type alias for our dataset shape
EvalDataset = Dataset[EvalInput, ReportExtraction, EvalMetadata]


def build_smoke_dataset() -> EvalDataset:
    """Build the smoke dataset from existing few-shot examples.

    Uses get_ct_abdomen_example() and get_xr_chest_example() from examples.py
    as ground truth, since they are hand-crafted reference extractions.
    """
    from finding_extractor.examples import get_ct_abdomen_example, get_xr_chest_example

    ct_text, ct_extraction = get_ct_abdomen_example()
    xr_text, xr_extraction = get_xr_chest_example()

    cases: list[Case[EvalInput, ReportExtraction, EvalMetadata]] = [
        Case(
            name="ct_abdomen_pelvis",
            inputs=EvalInput(report_text=ct_text),
            expected_output=ct_extraction,
            metadata=EvalMetadata(
                source_file="examples.py",
                modality="CT",
                body_region="abdomen",
            ),
        ),
        Case(
            name="xr_chest",
            inputs=EvalInput(report_text=xr_text),
            expected_output=xr_extraction,
            metadata=EvalMetadata(
                source_file="examples.py",
                modality="XR",
                body_region="chest",
            ),
        ),
    ]

    return Dataset(cases=cases)


def load_dataset(name_or_path: str) -> EvalDataset:
    """Load a dataset by name or file path.

    If name_or_path has no file extension, it is treated as a dataset name
    and resolved from the configured eval_dataset_dir (e.g., "smoke" ->
    "evals/datasets/smoke.yaml").

    Args:
        name_or_path: Dataset name (e.g., "smoke") or path to a YAML/JSON file.

    Returns:
        Loaded Dataset instance.

    Raises:
        FileNotFoundError: If the dataset file does not exist.
    """
    path = Path(name_or_path)

    if not path.suffix:
        # Treat as dataset name, resolve from config
        settings = get_settings()
        path = settings.eval_dataset_dir / f"{name_or_path}.yaml"

    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    return Dataset[EvalInput, ReportExtraction, EvalMetadata].from_file(str(path))
