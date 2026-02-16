"""Tests for modular extraction behavior in the orchestrator."""

import asyncio
from collections import defaultdict

import pytest

from finding_extractor.extraction_orchestrator import run_orchestrated_extraction
from finding_extractor.models import (
    ExamInfo,
    ExtractedFinding,
    ExtractionResult,
    ExtractionUsage,
    ReportExtraction,
    ValidationResult,
)
from finding_extractor.semantic_chunking import (
    ChunkingDiagnostics,
    ChunkingResult,
    ChunkingSettings,
    SectionChunk,
)


def _validation_ok(_report_text: str, _extraction: ReportExtraction) -> ValidationResult:
    return ValidationResult(is_valid=True, verbatim_errors=[], coverage_warnings=[])


@pytest.mark.asyncio
async def test_modular_pipeline_respects_section_concurrency_limit():
    """Section extraction should honor the configured bounded concurrency."""
    report_text = """Findings:
Stone in right kidney.
Impression:
Right nephrolithiasis.
Findings:
Left kidney clear.
"""
    statuses: list[str] = []
    in_flight = 0
    max_in_flight = 0
    seen_unit_texts: list[str] = []

    async def emit_status(message: str) -> None:
        statuses.append(message)

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        nonlocal in_flight, max_in_flight
        seen_unit_texts.append(report_text)
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        await asyncio.sleep(0.02)
        in_flight -= 1

        second_line = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name=f"finding-{second_line}",
                        presence="present",
                        report_text=second_line,
                    )
                ],
                non_finding_text=[],
            ),
            usage=ExtractionUsage(requests=1, input_tokens=10, output_tokens=5),
        )

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=False,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
    )

    assert max_in_flight == 2
    assert len(seen_unit_texts) == 3
    assert all(":" not in text.splitlines()[0] for text in seen_unit_texts)
    assert any("max_concurrency=2" in message for message in statuses)
    assert len(result.extraction.findings) == 3
    assert result.usage is not None
    assert result.usage.requests == 3
    assert result.pipeline_diagnostics.mode == "modular"
    assert result.pipeline_diagnostics.total_units == 3
    assert result.pipeline_diagnostics.initial_failed_units == 0
    assert result.pipeline_diagnostics.remaining_failed_units == 0
    assert result.pipeline_diagnostics.total_unit_attempts == 3


@pytest.mark.asyncio
async def test_modular_pipeline_retries_only_failed_sections():
    """Repair stage should retry only units that failed in the initial pass."""
    report_text = """Findings:
Stable 3 mm right renal stone.
Impression:
Persistent right nephrolithiasis.
"""
    statuses: list[str] = []
    attempts_by_section: dict[str, int] = defaultdict(int)

    async def emit_status(message: str) -> None:
        statuses.append(message)

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        header = report_text.splitlines()[0].strip().lower()
        attempts_by_section[header] += 1
        if "nephrolithiasis" in header and attempts_by_section[header] == 1:
            raise TimeoutError("transient timeout")

        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text.lower().replace(" ", "_"),
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=False,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        max_subagent_concurrency=2,
        unit_repair_attempts=1,
    )

    assert attempts_by_section["stable 3 mm right renal stone."] == 1
    assert attempts_by_section["persistent right nephrolithiasis."] == 2
    assert len(result.extraction.findings) == 2
    assert any(
        "extract_sections" in message and "unit=impression_1 attempt=1 status=failed" in message
        for message in statuses
    )
    assert any(
        "repair_failed_sections" in message
        and "unit=impression_1 attempt=1 status=completed" in message
        for message in statuses
    )
    assert result.pipeline_diagnostics.mode == "modular"
    assert result.pipeline_diagnostics.total_units == 2
    assert result.pipeline_diagnostics.initial_failed_units == 1
    assert result.pipeline_diagnostics.repaired_units == 1
    assert result.pipeline_diagnostics.remaining_failed_units == 0
    assert result.pipeline_diagnostics.repair_attempts_used == 1
    assert result.pipeline_diagnostics.total_unit_attempts == 3


@pytest.mark.asyncio
async def test_modular_pipeline_requires_findings_or_impression_sections():
    """Reports with parsed sections but no findings/impression should be rejected."""
    report_text = """Technique:
CT without contrast.
History:
Flank pain.
"""

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(**kwargs):  # noqa: ARG001
        raise AssertionError("extract_findings should not run")

    with pytest.raises(ValueError, match="No extractable `findings` or `impression` sections"):
        await run_orchestrated_extraction(
            report_text=report_text,
            exam_description=None,
            model_name="openai:gpt-5-mini",
            reasoning="medium",
            validate=False,
            coding_enabled=False,
            emit_status=emit_status,
            extract_findings_fn=fake_extract_findings,
            validate_extraction_fn=_validation_ok,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
        )


@pytest.mark.asyncio
async def test_modular_pipeline_supports_impression_only_reports():
    """Impression-only reports should produce a single extractable unit."""
    report_text = """Impression:
No acute cardiopulmonary abnormality.
"""
    seen_unit_texts: list[str] = []

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        seen_unit_texts.append(report_text)
        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CXR"),
                findings=[
                    ExtractedFinding(
                        finding_name="no acute cardiopulmonary abnormality",
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=False,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
    )

    assert len(seen_unit_texts) == 1
    assert seen_unit_texts[0].startswith("No acute cardiopulmonary abnormality.")
    assert len(result.extraction.findings) == 1
    assert result.pipeline_diagnostics.total_units == 1


@pytest.mark.asyncio
async def test_modular_pipeline_supports_findings_impression_combined_header():
    """Combined Findings/Impression header should still be extracted as one unit."""
    report_text = """Findings/Impression:
No focal airspace opacity.
No pleural effusion.
"""
    seen_unit_texts: list[str] = []

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        seen_unit_texts.append(report_text)
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CXR"),
                findings=[],
                non_finding_text=[],
            ),
            usage=None,
        )

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=False,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
    )

    assert len(seen_unit_texts) == 1
    assert seen_unit_texts[0].startswith("No focal airspace opacity.")
    assert result.pipeline_diagnostics.total_units == 1
    assert result.pipeline_diagnostics.initial_failed_units == 0


@pytest.mark.asyncio
async def test_modular_pipeline_dedupes_cross_section_findings_to_source_both():
    """Duplicate finding content across findings/impression should merge to source_section='both'."""
    report_text = """Findings:
There is a right renal calculus.
Impression:
There is a right renal calculus.
"""

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        finding_text = "There is a right renal calculus."
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name="renal calculus",
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=False,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
    )

    assert len(result.extraction.findings) == 1
    assert result.extraction.findings[0].source_section == "both"


@pytest.mark.asyncio
async def test_modular_pipeline_preserves_report_order_after_repair():
    """Recovered units should merge in report order, not retry completion order."""
    report_text = """Findings:
Right renal stone.
Impression:
Persistent nephrolithiasis.
"""
    attempts_by_section: dict[str, int] = defaultdict(int)

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        header = report_text.splitlines()[0].strip()
        attempts_by_section[header] += 1
        if header == "Right renal stone." and attempts_by_section[header] == 1:
            raise TimeoutError("transient failure")

        if header == "Right renal stone.":
            exam = "Exam from findings section"
            finding_name = "from-findings"
        else:
            exam = "Exam from impression section"
            finding_name = "from-impression"

        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description=exam),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_name,
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=False,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        max_subagent_concurrency=2,
        unit_repair_attempts=1,
    )

    assert attempts_by_section["Right renal stone."] == 2
    assert attempts_by_section["Persistent nephrolithiasis."] == 1
    assert [finding.finding_name for finding in result.extraction.findings] == [
        "from-findings",
        "from-impression",
    ]
    assert result.extraction.exam_info.study_description == "Exam from findings section"


@pytest.mark.asyncio
async def test_modular_pipeline_emits_remaining_failed_unit_diagnostics():
    """Repair exhaustion should expose parseable failed-unit diagnostics."""
    report_text = """Findings:
Right renal stone.
Impression:
Persistent nephrolithiasis.
"""
    statuses: list[str] = []

    async def emit_status(message: str) -> None:
        statuses.append(message)

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        header = report_text.splitlines()[0].strip()
        if header == "Persistent nephrolithiasis.":
            raise TimeoutError("persistent timeout")

        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name="from-findings",
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=False,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        max_subagent_concurrency=2,
        unit_repair_attempts=1,
    )

    assert len(result.extraction.findings) == 1
    assert result.pipeline_diagnostics.remaining_failed_units == 1
    assert result.pipeline_diagnostics.failed_unit_labels == ("impression_1",)
    assert result.pipeline_diagnostics.failed_unit_error_types == ("TimeoutError",)
    assert any(
        "repair_failed_sections" in message
        and "attempt=1 summary attempted_units=1 recovered_units=0 remaining_failed_units=1"
        in message
        for message in statuses
    )
    assert any(
        "repair_failed_sections" in message
        and "remaining_failed_units=1 labels=impression_1 errors=TimeoutError" in message
        for message in statuses
    )


@pytest.mark.asyncio
async def test_modular_pipeline_expands_sections_with_semantic_chunking(monkeypatch):
    """Enabled chunking should fan out one section into multiple extraction units."""
    report_text = """Findings:
Sentence one. Sentence two.
Impression:
Stable findings.
"""
    seen_unit_labels: list[str] = []

    async def fake_chunk_section_text(*, section_name: str, section_text: str, settings):  # noqa: ARG001
        if section_name == "findings":
            return ChunkingResult(
                chunks=(
                    SectionChunk(start_index=0, end_index=20, text="Findings:\nSentence one."),
                    SectionChunk(start_index=21, end_index=len(section_text), text="Sentence two."),
                ),
                diagnostics=ChunkingDiagnostics(
                    strategy="semantic_chunked",
                    chunk_count=2,
                    sentence_count=4,
                    semantic_applied=True,
                ),
            )
        return ChunkingResult(
            chunks=(SectionChunk(start_index=0, end_index=len(section_text), text=section_text),),
            diagnostics=ChunkingDiagnostics(
                strategy="sentence_only",
                chunk_count=1,
                sentence_count=1,
                semantic_applied=False,
            ),
        )

    monkeypatch.setattr(
        "finding_extractor.extraction_orchestrator.chunk_section_text",
        fake_chunk_section_text,
    )

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        seen_unit_labels.append(report_text.splitlines()[0].strip())
        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text.lower().replace(" ", "_"),
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=False,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
        chunking_settings=ChunkingSettings(enabled=True),
    )

    assert len(result.extraction.findings) == 3
    assert seen_unit_labels == ["Findings:", "Sentence two.", "Impression:"]
    assert result.pipeline_diagnostics.total_units == 3
