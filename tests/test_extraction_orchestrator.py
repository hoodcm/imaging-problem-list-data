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

        second_line = report_text.splitlines()[1].strip()
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
        modular_pipeline_enabled=True,
        section_max_concurrency=2,
        section_repair_attempts=0,
    )

    assert max_in_flight == 2
    assert len(seen_unit_texts) == 3
    assert all(text.startswith(("Findings:", "Impression:")) for text in seen_unit_texts)
    assert any("max_concurrency=2" in message for message in statuses)
    assert len(result.extraction.findings) == 3
    assert result.usage is not None
    assert result.usage.requests == 3


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
        if header.startswith("impression") and attempts_by_section[header] == 1:
            raise TimeoutError("transient timeout")

        finding_text = report_text.splitlines()[1].strip()
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
        modular_pipeline_enabled=True,
        section_max_concurrency=2,
        section_repair_attempts=1,
    )

    assert attempts_by_section["findings:"] == 1
    assert attempts_by_section["impression:"] == 2
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
        modular_pipeline_enabled=True,
        section_max_concurrency=2,
        section_repair_attempts=0,
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
        if header == "Findings:" and attempts_by_section[header] == 1:
            raise TimeoutError("transient failure")

        if header == "Findings:":
            exam = "Exam from findings section"
            finding_name = "from-findings"
        else:
            exam = "Exam from impression section"
            finding_name = "from-impression"

        finding_text = report_text.splitlines()[1].strip()
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
        modular_pipeline_enabled=True,
        section_max_concurrency=2,
        section_repair_attempts=1,
    )

    assert attempts_by_section["Findings:"] == 2
    assert attempts_by_section["Impression:"] == 1
    assert [finding.finding_name for finding in result.extraction.findings] == [
        "from-findings",
        "from-impression",
    ]
    assert result.extraction.exam_info.study_description == "Exam from findings section"
