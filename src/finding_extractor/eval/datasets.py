"""Dataset loading and building helpers for the evaluation harness."""

from __future__ import annotations

import json
from pathlib import Path

import structlog
from pydantic_evals import Case, Dataset

from finding_extractor.config import get_settings
from finding_extractor.eval.models import EvalInput, EvalMetadata
from finding_extractor.models import ReportExtraction

logger = structlog.get_logger(__name__)

# Type alias for our dataset shape
EvalDataset = Dataset[EvalInput, ReportExtraction, EvalMetadata]

# Keys added by batch CLI that are not part of ReportExtraction schema
_STRIP_KEYS = {"_validation", "_storage"}


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


def _infer_metadata(
    extraction: ReportExtraction, source_label: str
) -> EvalMetadata:
    """Infer EvalMetadata from a ReportExtraction's exam_info."""
    modality: str | None = None
    body_region: str | None = None
    if extraction.exam_info:
        modality = extraction.exam_info.modality
        body_region = extraction.exam_info.body_region
    return EvalMetadata(
        source_file=source_label,
        modality=modality,
        body_region=body_region,
    )


def _case_name_from_path(path: Path) -> str:
    """Derive a case name from a file path (stem, no extension)."""
    return path.stem


def import_baseline_cases(
    source_dir: Path,
    *,
    glob: str = "*.txt",
    output_suffix: str = ".extracted.json",
    source_label: str | None = None,
    model_filter: str | None = None,
) -> list[Case[EvalInput, ReportExtraction, EvalMetadata]]:
    """Import reviewed batch extraction results as ground truth eval cases.

    Scans source_dir for report files matching glob. For each report file,
    finds the corresponding extraction file (same stem + output_suffix),
    loads both, and builds a Case.

    Args:
        source_dir: Directory containing report + extraction file pairs.
        glob: Glob pattern for report files (default: "*.txt").
        output_suffix: Suffix convention for extraction files (default: ".extracted.json").
        source_label: Label for source_file metadata (default: directory basename).
        model_filter: Only import extractions from a specific model (checks _storage.model).

    Returns:
        List of Case objects ready for a Dataset.
    """
    source_dir = Path(source_dir).resolve()
    label = source_label or source_dir.name

    report_files = sorted(source_dir.glob(glob))
    if not report_files:
        logger.warning("no_report_files_found", source_dir=str(source_dir), glob=glob)
        return []

    cases: list[Case[EvalInput, ReportExtraction, EvalMetadata]] = []
    for report_path in report_files:
        extraction_path = report_path.parent / (report_path.stem + output_suffix)

        if not extraction_path.exists():
            logger.warning(
                "extraction_file_missing",
                report=report_path.name,
                expected=extraction_path.name,
            )
            continue

        try:
            raw = json.loads(extraction_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning(
                "extraction_file_parse_error",
                file=extraction_path.name,
                error=str(exc),
            )
            continue

        # Optional model filter (check _storage before stripping)
        if model_filter:
            storage = raw.get("_storage", {})
            file_model = storage.get("model")
            if file_model and file_model != model_filter:
                logger.info(
                    "skipping_model_mismatch",
                    file=extraction_path.name,
                    file_model=file_model,
                    filter=model_filter,
                )
                continue

        # Strip non-schema keys
        for key in _STRIP_KEYS:
            raw.pop(key, None)

        try:
            extraction = ReportExtraction.model_validate(raw)
        except Exception as exc:
            logger.warning(
                "extraction_validation_error",
                file=extraction_path.name,
                error=str(exc),
            )
            continue

        report_text = report_path.read_text(encoding="utf-8")
        metadata = _infer_metadata(extraction, label)
        case_name = _case_name_from_path(report_path)

        cases.append(
            Case(
                name=case_name,
                inputs=EvalInput(report_text=report_text),
                expected_output=extraction,
                metadata=metadata,
            )
        )

    logger.info("imported_cases", count=len(cases), source_dir=str(source_dir))
    return cases


def save_dataset(dataset: EvalDataset, name_or_path: str) -> Path:
    """Save a dataset to a YAML file.

    If name_or_path has no file extension, it is treated as a dataset name
    and resolved to the configured eval_dataset_dir.

    Returns:
        Path to the written file.
    """
    path = Path(name_or_path)
    if not path.suffix:
        settings = get_settings()
        path = settings.eval_dataset_dir / f"{name_or_path}.yaml"

    path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_file(str(path))
    return path


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
