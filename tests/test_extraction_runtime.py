"""Tests for shared extraction runtime wiring."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from finding_extractor.extraction_orchestrator import (
    OrchestratedExtractionResult,
    PipelineDiagnostics,
)
from finding_extractor.extraction_runtime import run_extraction_runtime
from finding_extractor.models import ExamInfo, ReportExtraction


def _empty_orchestrated_result() -> OrchestratedExtractionResult:
    extraction = ReportExtraction(
        exam_info=ExamInfo(study_description="CT"),
        findings=[],
        non_finding_text=[],
    )
    return OrchestratedExtractionResult(
        extraction=extraction,
        usage=None,
        validation_result=None,
        pipeline_diagnostics=PipelineDiagnostics(
            mode="modular",
            total_units=1,
            initial_failed_units=0,
            repaired_units=0,
            remaining_failed_units=0,
            repair_attempts_used=0,
            total_unit_attempts=1,
            failed_unit_labels=(),
            failed_unit_error_types=(),
        ),
    )


def _runtime_settings(**overrides):
    base = {
        "default_model": "openai:gpt-5-mini",
        "validator_model": None,
        "validator_reasoning": "minimal",
        "validator_reextract_enabled": True,
        "extractor_max_subagent_concurrency": 5,
        "extractor_chunk_repair_enabled": True,
        "chunking_semantic_trigger_sentence_count": 4,
        "chunking_semantic_embedding_model": "minishlab/potion-base-32M",
        "chunking_semantic_threshold": 0.8,
        "chunking_semantic_chunk_size": 2048,
        "chunking_semantic_similarity_window": 3,
        "chunking_semantic_skip_window": 0,
        "chunking_impression_list_chunking_enabled": True,
        "chunking_impression_list_max_items_per_chunk": 3,
        "chunking_impression_list_min_items_per_chunk": 2,
        "subagent_timeout_seconds": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


@pytest.mark.asyncio
async def test_runtime_enables_validator_review_without_validator_model(monkeypatch):
    observed: dict[str, object] = {}

    async def _fake_orchestrator(**kwargs):
        observed.update(kwargs)
        return _empty_orchestrated_result()

    monkeypatch.setattr(
        "finding_extractor.extraction_runtime.run_orchestrated_extraction",
        _fake_orchestrator,
    )

    settings = _runtime_settings(

        validator_model=None,
        validator_reextract_enabled=True,
    )

    await run_extraction_runtime(
        report_text="Findings:\nNo acute findings.",
        exam_type=None,
        model="openai:gpt-5-mini",
        reasoning=None,
        validate=False,
        settings=settings,
    )

    assert observed["review_chunks_fn"] is not None
    assert observed["validator_reextract_enabled"] is True


@pytest.mark.asyncio
async def test_runtime_keeps_validator_review_when_reextract_disabled(monkeypatch):
    observed: dict[str, object] = {}

    async def _fake_orchestrator(**kwargs):
        observed.update(kwargs)
        return _empty_orchestrated_result()

    monkeypatch.setattr(
        "finding_extractor.extraction_runtime.run_orchestrated_extraction",
        _fake_orchestrator,
    )

    settings = _runtime_settings(

        validator_reextract_enabled=False,
    )

    await run_extraction_runtime(
        report_text="Findings:\nNo acute findings.",
        exam_type=None,
        model="openai:gpt-5-mini",
        reasoning=None,
        validate=False,
        settings=settings,
    )

    assert observed["review_chunks_fn"] is not None
    assert observed["validator_reextract_enabled"] is False


@pytest.mark.asyncio
async def test_runtime_forwards_source_ref_to_exam_info_path(monkeypatch):
    observed: dict[str, object] = {}

    async def _fake_orchestrator(**kwargs):
        observed.update(kwargs)
        return _empty_orchestrated_result()

    monkeypatch.setattr(
        "finding_extractor.extraction_runtime.run_orchestrated_extraction",
        _fake_orchestrator,
    )

    settings = _runtime_settings(

        validator_reextract_enabled=True,
    )

    await run_extraction_runtime(
        report_text="Findings:\nNo acute findings.",
        exam_type="CT Chest",
        model="openai:gpt-5-mini",
        reasoning=None,
        validate=False,
        source_ref="sample_data/example2/ct_chest_foo.md",
        report_id="report-123",
        settings=settings,
    )

    assert observed["source_ref"] == "sample_data/example2/ct_chest_foo.md"
    assert observed["external_metadata"] == {"report_id": "report-123"}
    assert observed["review_chunks_fn"] is not None
