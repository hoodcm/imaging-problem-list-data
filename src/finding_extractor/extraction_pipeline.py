"""Shared extraction pipeline for CLI entry points."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from finding_extractor.agent import (
    extract_findings,
    validate_extraction,
)
from finding_extractor.config import get_settings
from finding_extractor.model_policy import validate_model_id
from finding_extractor.models import ExtractionUsage, ReportExtraction, ValidationResult
from finding_extractor.providers import resolve_effective_reasoning
from finding_extractor.store import ExtractionStore


@dataclass(frozen=True)
class StorageMetadata:
    """Persistence metadata returned from an extraction pipeline run."""

    db_path: str
    report_id: str
    report_seen_before: bool
    extraction_id: str
    model_name: str
    reasoning_effort: str | None
    extracted_at: str
    usage: ExtractionUsage | None = None


def resolve_model_name(model: str | None) -> str:
    """Resolve effective model for extraction requests."""
    return model or get_settings().default_model


def resolve_db_path(db_path: Path | None) -> Path:
    """Resolve persistence path from option/env/default."""
    if db_path is not None:
        return db_path
    return get_settings().db_path


async def run_extraction_pipeline(
    report_text: str,
    *,
    exam_type: str | None,
    model: str | None,
    reasoning: str | None,
    validate: bool,
    store: ExtractionStore | None,
    db_path: Path | None,
    source_ref: str | None,
    status_callback: Callable[[str], Awaitable[None]] | None = None,
) -> tuple[ReportExtraction, ValidationResult | None, StorageMetadata | None]:
    """Run extraction, optional validation, and optional persistence."""

    async def _emit(message: str) -> None:
        if status_callback is not None:
            await status_callback(message)

    await _emit("Validating model configuration...")
    model_name = resolve_model_name(model)
    validate_model_id(model_name)
    effective_reasoning = resolve_effective_reasoning(model_name, reasoning)

    extraction_result = await extract_findings(
        report_text=report_text,
        exam_description=exam_type,
        model=model_name,
        reasoning=effective_reasoning,
        status_callback=status_callback,
    )
    extraction = extraction_result.extraction
    usage = extraction_result.usage

    if validate:
        await _emit("Validating extraction results...")
    validation_result: ValidationResult | None = (
        validate_extraction(report_text, extraction) if validate else None
    )

    storage_metadata: StorageMetadata | None = None
    if store is not None:
        await _emit("Saving to database...")
        resolved_db_path = resolve_db_path(db_path)
        report_record = await store.upsert_report(
            report_text=report_text,
            source_ref=source_ref,
        )
        extraction_record = await store.create_extraction(
            report_id=report_record.id,
            extraction=extraction,
            model_name=model_name,
            reasoning_effort=effective_reasoning,
            exam_description_hint=exam_type,
            validation_result=validation_result,
            usage=usage,
        )
        storage_metadata = StorageMetadata(
            db_path=str(resolved_db_path),
            report_id=report_record.id,
            report_seen_before=report_record.seen_before,
            extraction_id=extraction_record.id,
            model_name=model_name,
            reasoning_effort=effective_reasoning,
            extracted_at=extraction_record.created_at,
            usage=usage,
        )

    await _emit("Done.")
    return extraction, validation_result, storage_metadata
