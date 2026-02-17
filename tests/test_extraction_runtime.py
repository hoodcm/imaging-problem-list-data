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
        "coding_model": None,
        "coding_adjudication_enabled": True,
        "coding_reasoning": "none",
        "coding_max_concurrency": 5,
        "coding_enabled": False,
        "validator_review_enabled": False,
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
        coding_enabled=False,
        validator_review_enabled=True,
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
async def test_runtime_disables_validator_review_when_flag_off(monkeypatch):
    observed: dict[str, object] = {}

    async def _fake_orchestrator(**kwargs):
        observed.update(kwargs)
        return _empty_orchestrated_result()

    monkeypatch.setattr(
        "finding_extractor.extraction_runtime.run_orchestrated_extraction",
        _fake_orchestrator,
    )

    settings = _runtime_settings(
        coding_enabled=False,
        validator_review_enabled=False,
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

    assert observed["review_chunks_fn"] is None
    assert observed["validator_reextract_enabled"] is False


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
        coding_enabled=False,
        validator_review_enabled=True,
        validator_model=None,
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
async def test_runtime_normalizes_openai_gpt5_coding_reasoning(monkeypatch):
    observed: dict[str, object] = {}
    captured_coding_args: dict[str, object] = {}

    async def _fake_orchestrator(**kwargs):
        observed.update(kwargs)
        return _empty_orchestrated_result()

    async def _fake_apply_coding(extraction, **kwargs):
        _ = extraction
        captured_coding_args.update(kwargs)
        return extraction

    monkeypatch.setattr(
        "finding_extractor.extraction_runtime.run_orchestrated_extraction",
        _fake_orchestrator,
    )
    monkeypatch.setattr("finding_extractor.coding_bridge.apply_coding", _fake_apply_coding)

    settings = _runtime_settings(
        coding_enabled=True,
        coding_model="openai:gpt-5-mini",
        coding_reasoning="none",
        coding_adjudication_enabled=True,
    )

    await run_extraction_runtime(
        report_text="Findings:\nNo acute findings.",
        exam_type=None,
        model="openai:gpt-5-mini",
        reasoning=None,
        validate=False,
        settings=settings,
    )

    apply_coding_fn = observed["apply_coding_fn"]
    assert apply_coding_fn is not None
    await apply_coding_fn(_empty_orchestrated_result().extraction)

    assert captured_coding_args["adjudicator_model"] == "openai:gpt-5-mini"
    assert captured_coding_args["adjudicator_reasoning"] == "minimal"
