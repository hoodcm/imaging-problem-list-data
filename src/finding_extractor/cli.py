"""CLI for the finding extraction agent.

Usage:
    finding-extractor <report_file> [OPTIONS]

Options:
    --exam-type TEXT      Exam description for context
    --output PATH         Output JSON file (default: stdout)
    --model TEXT          LLM model override (default: openai:gpt-5-mini)
    --reasoning TEXT      Reasoning effort: "none", "minimal", "low", "medium", "high"
    --format TEXT         Output: "json" (default) or "table" (summary)
    --validate            Run post-extraction validation
    --store               Persist report/extraction metadata to SQLite
    --db-path PATH        SQLite path (default: FINDING_EXTRACTOR_DB_PATH or .finding_extractor.db)
"""

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import click
from asyncer import runnify

from finding_extractor.agent import extract_findings, validate_extraction
from finding_extractor.config import get_settings
from finding_extractor.models import ReportExtraction, ValidationResult
from finding_extractor.store import ExtractionStore


@dataclass(frozen=True)
class StorageMetadata:
    """Persistence metadata returned from one CLI run."""

    db_path: str
    report_id: str
    report_seen_before: bool
    extraction_id: str
    model_name: str
    reasoning_effort: str | None
    extracted_at: str


def _resolve_model_name(model: str | None) -> str:
    """Resolve effective model for provenance metadata."""
    return model or get_settings().default_model


def _resolve_db_path(db_path: Path | None) -> Path:
    """Resolve persistence path from CLI option, env var, then default."""
    if db_path is not None:
        return db_path
    return get_settings().db_path


async def _run_pipeline(
    report_text: str,
    *,
    exam_type: str | None,
    model: str | None,
    reasoning: str | None,
    validate: bool,
    store: bool,
    db_path: Path | None,
    source_ref: str | None,
) -> tuple[ReportExtraction, ValidationResult | None, StorageMetadata | None]:
    """Run extraction, optional validation, and optional persistence."""
    extraction = await extract_findings(
        report_text=report_text,
        exam_description=exam_type,
        model=model,
        reasoning=reasoning,
    )

    validation_result: ValidationResult | None = (
        validate_extraction(report_text, extraction) if validate else None
    )
    storage_metadata: StorageMetadata | None = None

    if store:
        resolved_db_path = _resolve_db_path(db_path)
        model_name = _resolve_model_name(model)
        extraction_store = ExtractionStore(resolved_db_path)
        try:
            report_record = await extraction_store.upsert_report(
                report_text=report_text,
                source_ref=source_ref,
            )
            extraction_record = await extraction_store.create_extraction(
                report_id=report_record.id,
                extraction=extraction,
                model_name=model_name,
                reasoning_effort=reasoning,
                exam_description_hint=exam_type,
                validation_result=validation_result,
            )
            storage_metadata = StorageMetadata(
                db_path=str(resolved_db_path),
                report_id=report_record.id,
                report_seen_before=report_record.seen_before,
                extraction_id=extraction_record.id,
                model_name=model_name,
                reasoning_effort=reasoning,
                extracted_at=extraction_record.created_at,
            )
        finally:
            await extraction_store.close()

    return extraction, validation_result, storage_metadata


_run_pipeline_sync = runnify(_run_pipeline)


@click.command()
@click.argument("report_file", type=click.File("r"))
@click.option(
    "--exam-type",
    help="Exam description for context (e.g., modality, body part)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output JSON file (default: stdout)",
)
@click.option(
    "--model",
    "-m",
    help="LLM model override (default: openai:gpt-5-mini or FINDING_EXTRACTOR_MODEL env var)",
)
@click.option(
    "--reasoning",
    "-r",
    type=click.Choice(["none", "minimal", "low", "medium", "high"], case_sensitive=False),
    help="Reasoning effort level",
)
@click.option(
    "--format",
    "-f",
    "output_format",
    type=click.Choice(["json", "table"], case_sensitive=False),
    default="json",
    help="Output format (default: json)",
)
@click.option(
    "--validate/--no-validate",
    default=False,
    help="Run post-extraction validation (default: no-validate)",
)
@click.option(
    "--store/--no-store",
    default=False,
    help="Persist report and extraction metadata to SQLite (default: no-store)",
)
@click.option(
    "--db-path",
    type=click.Path(path_type=Path),
    help="SQLite path (default: FINDING_EXTRACTOR_DB_PATH or .finding_extractor.db)",
)
def main(
    report_file,
    exam_type,
    output,
    model,
    reasoning,
    output_format,
    validate,
    store,
    db_path,
):
    """Extract structured findings from a radiology report.

    REPORT_FILE is the path to the radiology report text file.
    """
    report_text = report_file.read()

    try:
        extraction, validation_result, storage_metadata = _run_pipeline_sync(
            report_text=report_text,
            exam_type=exam_type,
            model=model,
            reasoning=reasoning,
            validate=validate,
            store=store,
            db_path=db_path,
            source_ref=report_file.name,
        )

        if output_format == "json":
            output_text = format_json_output(
                extraction,
                validation_result,
                storage_metadata,
            )
        else:
            output_text = format_table_output(
                extraction,
                validation_result,
                storage_metadata,
            )

        if output:
            output.write_text(output_text)
            click.echo(f"Output written to {output}")
        else:
            click.echo(output_text)

        if validate and validation_result is not None and not validation_result.is_valid:
            sys.exit(2)
    except Exception as e:
        click.echo(f"Error during extraction: {e}", err=True)
        sys.exit(1)


def format_json_output(
    extraction: ReportExtraction,
    validation_result: ValidationResult | None = None,
    storage_metadata: StorageMetadata | None = None,
) -> str:
    """Format extraction as JSON output."""
    data = extraction.model_dump(mode="json")

    if validation_result is not None:
        data["_validation"] = validation_result.model_dump(mode="json")
    if storage_metadata:
        data["_storage"] = asdict(storage_metadata)

    return json.dumps(data, indent=2)


def format_table_output(
    extraction: ReportExtraction,
    validation_result: ValidationResult | None = None,
    storage_metadata: StorageMetadata | None = None,
) -> str:
    """Format extraction as human-readable table/summary."""
    lines = []

    lines.append("=" * 70)
    lines.append("RADIOLOGY REPORT EXTRACTION")
    lines.append("=" * 70)
    lines.append("")

    lines.append(f"Study: {extraction.exam_info.study_description}")
    if extraction.exam_info.study_date:
        lines.append(f"Date: {extraction.exam_info.study_date}")
    if extraction.exam_info.modality:
        lines.append(f"Modality: {extraction.exam_info.modality}")
    if extraction.exam_info.body_part:
        lines.append(f"Body Part: {extraction.exam_info.body_part}")
    lines.append("")

    present = [f for f in extraction.findings if f.presence == "present"]
    absent = [f for f in extraction.findings if f.presence == "absent"]
    possible = [f for f in extraction.findings if f.presence == "possible"]
    indeterminate = [f for f in extraction.findings if f.presence == "indeterminate"]

    lines.append("-" * 70)
    lines.append(f"FINDINGS SUMMARY: {len(extraction.findings)} total")
    lines.append(
        f"  Present: {len(present)} | Absent: {len(absent)}"
        f" | Possible: {len(possible)} | Indeterminate: {len(indeterminate)}"
    )
    lines.append("-" * 70)
    lines.append("")

    if present:
        lines.append("PRESENT FINDINGS:")
        lines.append("")
        for i, finding in enumerate(present, 1):
            lines.append(f"  {i}. {finding.finding_name}")
            if finding.location:
                loc_parts = [finding.location.body_region]
                if finding.location.specific_anatomy:
                    loc_parts.append(finding.location.specific_anatomy)
                if finding.location.laterality:
                    loc_parts.append(f"({finding.location.laterality})")
                lines.append(f"     Location: {' - '.join(loc_parts)}")
            if finding.attributes:
                attrs = ", ".join(f"{a.key}={a.value}" for a in finding.attributes)
                lines.append(f"     Attributes: {attrs}")
            text_preview = finding.report_text[:60]
            ellipsis = "..." if len(finding.report_text) > 60 else ""
            lines.append(f'     Text: "{text_preview}{ellipsis}"')
            lines.append("")

    if absent:
        lines.append("ABSENT FINDINGS (ruled out):")
        absent_names = [f.finding_name for f in absent]
        for i in range(0, len(absent_names), 4):
            chunk = absent_names[i : i + 4]
            lines.append(f"  {', '.join(chunk)}")
        lines.append("")

    if possible:
        lines.append("POSSIBLE FINDINGS (hedged/uncertain):")
        for finding in possible:
            lines.append(f"  - {finding.finding_name}")
        lines.append("")

    if extraction.non_finding_text:
        lines.append("-" * 70)
        lines.append(f"NON-FINDING TEXT: {len(extraction.non_finding_text)} segments")
        categories: dict[str, int] = {}
        for nft in extraction.non_finding_text:
            categories[nft.category] = categories.get(nft.category, 0) + 1
        for cat, count in sorted(categories.items()):
            lines.append(f"  {cat}: {count}")
        lines.append("")

    if validation_result:
        lines.append("-" * 70)
        lines.append("VALIDATION:")
        if validation_result.is_valid:
            lines.append("  Status: PASSED")
        else:
            lines.append("  Status: FAILED")

        if validation_result.verbatim_errors:
            lines.append(f"  Verbatim Errors: {len(validation_result.verbatim_errors)}")
            for error in validation_result.verbatim_errors[:3]:
                lines.append(f"    - {error[:80]}")
            if len(validation_result.verbatim_errors) > 3:
                lines.append(f"    ... and {len(validation_result.verbatim_errors) - 3} more")

        if validation_result.coverage_warnings:
            lines.append(f"  Coverage Warnings: {len(validation_result.coverage_warnings)}")
            for warning in validation_result.coverage_warnings[:2]:
                lines.append(f"    - {warning[:80]}")
        lines.append("")

    if storage_metadata:
        lines.append("-" * 70)
        lines.append("PERSISTENCE:")
        lines.append(f"  DB Path: {storage_metadata.db_path}")
        lines.append(f"  Report ID: {storage_metadata.report_id}")
        lines.append(f"  Seen Before: {storage_metadata.report_seen_before}")
        lines.append(f"  Extraction ID: {storage_metadata.extraction_id}")
        lines.append(f"  Model: {storage_metadata.model_name}")
        lines.append(f"  Timestamp: {storage_metadata.extracted_at}")
        lines.append("")

    lines.append("=" * 70)

    return "\n".join(lines)


if __name__ == "__main__":
    main()
