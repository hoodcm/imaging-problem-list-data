"""Tests for modular extraction behavior in the orchestrator."""

import asyncio
from collections import defaultdict

import pytest

from finding_extractor.extraction_orchestrator import (
    UnitReextractionRequest,
    ValidationReviewDecision,
    run_orchestrated_extraction,
)
from finding_extractor.models import (
    ExamInfo,
    ExtractedFinding,
    ExtractionResult,
    ExtractionUsage,
    FindingCode,
    FindingCodingBundle,
    LocationCode,
    NonFindingText,
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
async def test_modular_pipeline_drops_non_finding_text_that_duplicates_finding_span():
    """Merged output should not keep duplicate span text in non_finding_text."""
    report_text = """Impression:
No acute cardiopulmonary process.
"""

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        finding_text = "No acute cardiopulmonary process."
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CXR"),
                findings=[
                    ExtractedFinding(
                        finding_name="acute cardiopulmonary process",
                        presence="absent",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[
                    NonFindingText(text=finding_text, category="impression"),
                    NonFindingText(text="Technique: AP portable chest.", category="technique"),
                ],
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
    assert result.extraction.findings[0].report_text == "No acute cardiopulmonary process."
    assert [span.text for span in result.extraction.non_finding_text] == [
        "Technique: AP portable chest."
    ]


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
        chunking_settings=ChunkingSettings(),
    )

    assert len(result.extraction.findings) == 3
    assert seen_unit_labels == ["Findings:", "Sentence two.", "Impression:"]
    assert result.pipeline_diagnostics.total_units == 3


@pytest.mark.asyncio
async def test_modular_pipeline_starts_unit_coding_before_all_extractions_finish():
    """Coding should start as soon as a unit extraction completes."""
    report_text = """Findings:
fast finding.
Impression:
slow finding.
"""
    extract_completed_at: dict[str, float] = {}
    coding_started_at: dict[str, float] = {}

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        finding_text = report_text.splitlines()[-1].strip().lower()
        if "slow" in finding_text:
            await asyncio.sleep(0.08)
        else:
            await asyncio.sleep(0.01)
        extract_completed_at[finding_text] = asyncio.get_running_loop().time()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CXR"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text,
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    async def fake_apply_coding(extraction: ReportExtraction) -> ReportExtraction:
        finding_text = extraction.findings[0].report_text.strip().lower()
        coding_started_at.setdefault(finding_text, asyncio.get_running_loop().time())
        await asyncio.sleep(0.01)
        coded_finding = extraction.findings[0].model_copy(
            update={
                "coding": FindingCodingBundle(
                    finding_code=FindingCode(
                        status="coded",
                        oifm_id=f"OIFM_{finding_text.replace(' ', '_').upper()}",
                        oifm_name=finding_text,
                        method="exact",
                    ),
                    location_code=LocationCode(),
                )
            }
        )
        return extraction.model_copy(update={"findings": [coded_finding]})

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=True,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        apply_coding_fn=fake_apply_coding,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
    )

    assert result.extraction.findings[0].coding is not None
    assert coding_started_at["fast finding."] < extract_completed_at["slow finding."]


@pytest.mark.asyncio
async def test_modular_pipeline_latest_reextract_coding_supersedes_earlier_unit_result():
    """Coding from validator-triggered re-extraction should replace prior unit coding."""
    report_text = """Findings:
finding to revise.
"""
    extract_calls = 0

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        nonlocal extract_calls
        extract_calls += 1
        finding_text = "initial finding." if extract_calls == 1 else "updated finding."
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text,
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    async def fake_review_chunks(**kwargs):  # noqa: ARG001
        return ValidationReviewDecision(
            reextract_requests=(UnitReextractionRequest(label="findings_1"),),
            rationale="refresh unit",
        )

    async def fake_apply_coding(extraction: ReportExtraction) -> ReportExtraction:
        finding_text = extraction.findings[0].report_text.strip().lower()
        oifm_id = "OIFM_UPDATED" if "updated" in finding_text else "OIFM_INITIAL"
        coded_finding = extraction.findings[0].model_copy(
            update={
                "coding": FindingCodingBundle(
                    finding_code=FindingCode(
                        status="coded",
                        oifm_id=oifm_id,
                        oifm_name=finding_text,
                        method="exact",
                    ),
                    location_code=LocationCode(),
                )
            }
        )
        return extraction.model_copy(update={"findings": [coded_finding]})

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=True,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        apply_coding_fn=fake_apply_coding,
        review_chunks_fn=fake_review_chunks,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
        validator_reextract_enabled=True,
    )

    assert extract_calls == 2
    assert result.extraction.findings[0].report_text == "updated finding."
    assert result.extraction.findings[0].coding is not None
    assert result.extraction.findings[0].coding.finding_code.oifm_id == "OIFM_UPDATED"


@pytest.mark.asyncio
async def test_modular_pipeline_runs_validator_review_when_reextract_disabled():
    """Validator review should still run even when re-extract is disabled."""
    report_text = """Findings:
finding to review.
"""
    extract_calls = 0
    review_calls = 0
    statuses: list[str] = []

    async def emit_status(message: str) -> None:
        statuses.append(message)

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        nonlocal extract_calls
        extract_calls += 1
        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text,
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    async def fake_review_chunks(**kwargs):  # noqa: ARG001
        nonlocal review_calls
        review_calls += 1
        return ValidationReviewDecision(
            reextract_requests=(UnitReextractionRequest(label="findings_1"),),
            rationale="would reextract if enabled",
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
        review_chunks_fn=fake_review_chunks,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
        validator_reextract_enabled=False,
    )

    assert review_calls == 1
    assert extract_calls == 1
    assert result.pipeline_diagnostics.validator_requested_units == 1
    assert result.pipeline_diagnostics.validator_reextracted_units == 0
    assert any(
        "validator_review" in message
        and "reextract_disabled requested=1 labels=findings_1" in message
        for message in statuses
    )


@pytest.mark.asyncio
async def test_modular_pipeline_aligns_inline_coding_to_merged_finding_order():
    """Final inline coding should align to merged/deduped finding order and count."""
    report_text = """Findings:
First finding.
Second finding.
Impression:
Second finding.
"""

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        lowered = report_text.lower()
        if "first finding." in lowered:
            findings = [
                ExtractedFinding(
                    finding_name="first finding",
                    presence="present",
                    report_text="First finding.",
                ),
                ExtractedFinding(
                    finding_name="second finding",
                    presence="present",
                    report_text="Second finding.",
                ),
            ]
        else:
            findings = [
                ExtractedFinding(
                    finding_name="second finding",
                    presence="present",
                    report_text="Second finding.",
                )
            ]

        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=findings,
                non_finding_text=[],
            ),
            usage=None,
        )

    async def fake_apply_coding(extraction: ReportExtraction) -> ReportExtraction:
        mapping = {
            "first finding": "OIFM_FIRST",
            "second finding": "OIFM_SECOND",
        }
        coded_findings = [
            finding.model_copy(
                update={
                    "coding": FindingCodingBundle(
                        finding_code=FindingCode(
                            status="coded",
                            oifm_id=mapping[finding.finding_name],
                            oifm_name=finding.finding_name,
                            method="exact",
                        ),
                        location_code=LocationCode(),
                    )
                }
            )
            for finding in extraction.findings
        ]
        return extraction.model_copy(update={"findings": coded_findings})

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description=None,
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=True,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        apply_coding_fn=fake_apply_coding,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
    )

    assert [finding.finding_name for finding in result.extraction.findings] == [
        "first finding",
        "second finding",
    ]
    assert all(finding.coding is not None for finding in result.extraction.findings)
    assert [
        finding.coding.finding_code.oifm_id
        for finding in result.extraction.findings
        if finding.coding is not None
    ] == [
        "OIFM_FIRST",
        "OIFM_SECOND",
    ]


@pytest.mark.asyncio
async def test_modular_pipeline_chunk_extraction_timeout_recorded_as_error():
    """Chunk extraction timeout should be recorded as TimeoutError in diagnostics."""
    report_text = """Findings:
Right renal stone.
Impression:
Persistent nephrolithiasis.
"""

    async def emit_status(_message: str) -> None:
        return None

    async def slow_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        await asyncio.sleep(0.5)  # Exceeds timeout
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT"),
                findings=[
                    ExtractedFinding(
                        finding_name="test",
                        presence="present",
                        report_text=report_text.splitlines()[-1].strip(),
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    with pytest.raises((TimeoutError, RuntimeError)):
        await run_orchestrated_extraction(
            report_text=report_text,
            exam_description=None,
            model_name="openai:gpt-5-mini",
            reasoning="medium",
            validate=False,
            coding_enabled=False,
            emit_status=emit_status,
            extract_findings_fn=slow_extract_findings,
            validate_extraction_fn=_validation_ok,
            max_subagent_concurrency=2,
            unit_repair_attempts=0,
            subagent_timeout_seconds=0.05,
        )


@pytest.mark.asyncio
async def test_modular_pipeline_no_timeout_when_none():
    """None timeout should not enforce any deadline."""
    report_text = """Findings:
Normal finding.
"""

    async def emit_status(_message: str) -> None:
        return None

    async def fast_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        await asyncio.sleep(0.01)
        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text,
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
        extract_findings_fn=fast_extract_findings,
        validate_extraction_fn=_validation_ok,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
        subagent_timeout_seconds=None,
    )

    assert len(result.extraction.findings) == 1


@pytest.mark.asyncio
async def test_modular_pipeline_exam_info_parallel_execution():
    """Exam-info fn should run in parallel with chunk extraction."""
    exam_info_started_at = 0.0
    extract_started_at = 0.0

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_exam_info(
        report_text: str,  # noqa: ARG001
        *,
        exam_description: str | None = None,  # noqa: ARG001
        source_ref: str | None = None,  # noqa: ARG001
        external_metadata: dict[str, str] | None = None,  # noqa: ARG001
        report_headers: str | None = None,  # noqa: ARG001
    ):
        nonlocal exam_info_started_at
        exam_info_started_at = asyncio.get_running_loop().time()
        await asyncio.sleep(0.02)
        return ExamInfo(study_description="CT Abdomen", modality="CT", body_part="abdomen")

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        nonlocal extract_started_at
        extract_started_at = asyncio.get_running_loop().time()
        await asyncio.sleep(0.02)
        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="placeholder"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text,
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    report_text = """Findings:
Right renal stone.
"""

    result = await run_orchestrated_extraction(
        report_text=report_text,
        exam_description="CT Abdomen",
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=False,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        extract_exam_info_fn=fake_extract_exam_info,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
    )

    assert result.extraction.exam_info.modality == "CT"
    assert result.extraction.exam_info.body_part == "abdomen"
    # Both should have started at roughly the same time (parallel)
    assert abs(exam_info_started_at - extract_started_at) < 0.1


@pytest.mark.asyncio
async def test_modular_pipeline_passes_exam_info_context_inputs():
    """Exam-info sub-agent should receive source_ref, metadata, and header-focused text."""
    captured: dict[str, object] = {}

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_exam_info(
        report_text: str,
        *,
        exam_description: str | None = None,
        source_ref: str | None = None,
        external_metadata: dict[str, str] | None = None,
        report_headers: str | None = None,
    ):
        captured.update(
            {
                "report_text": report_text,
                "exam_description": exam_description,
                "source_ref": source_ref,
                "external_metadata": external_metadata,
                "report_headers": report_headers,
            }
        )
        return ExamInfo(study_description="CT Abdomen", modality="CT", body_part="abdomen")

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="placeholder"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text,
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    report_text = """Indication: flank pain
Comparison: prior study
Findings:
Right renal stone.
Impression:
Right nephrolithiasis.
"""

    await run_orchestrated_extraction(
        report_text=report_text,
        exam_description="CT Abdomen",
        model_name="openai:gpt-5-mini",
        reasoning="medium",
        validate=False,
        coding_enabled=False,
        emit_status=emit_status,
        extract_findings_fn=fake_extract_findings,
        validate_extraction_fn=_validation_ok,
        extract_exam_info_fn=fake_extract_exam_info,
        source_ref="sample_data/example2/ct_abdomen_20230118.md",
        external_metadata={"report_id": "r-1"},
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
    )

    assert captured["source_ref"] == "sample_data/example2/ct_abdomen_20230118.md"
    assert captured["external_metadata"] == {"report_id": "r-1"}
    report_headers = captured.get("report_headers")
    assert isinstance(report_headers, str)
    assert "Indication: flank pain" in report_headers
    assert "Comparison: prior study" in report_headers
    assert "Right renal stone." not in report_headers


@pytest.mark.asyncio
async def test_modular_pipeline_exam_info_failure_nonfatal():
    """Exam-info failure should be non-fatal — pipeline keeps placeholder exam_info."""

    async def emit_status(_message: str) -> None:
        return None

    async def failing_extract_exam_info(**kwargs):  # noqa: ARG001
        raise RuntimeError("exam info agent failed")

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="placeholder"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text,
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    report_text = """Findings:
Normal finding.
"""

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
        extract_exam_info_fn=failing_extract_exam_info,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
    )

    # Should still succeed with placeholder exam_info
    assert len(result.extraction.findings) == 1
    assert result.extraction.exam_info.study_description == "placeholder"


@pytest.mark.asyncio
async def test_modular_pipeline_exam_info_signature_mismatch_nonfatal():
    """Outdated exam-info callable signatures should fail non-fatally."""
    statuses: list[str] = []

    async def emit_status(message: str) -> None:
        statuses.append(message)

    async def legacy_extract_exam_info(
        report_text: str,  # noqa: ARG001
        *,
        exam_description: str | None = None,  # noqa: ARG001
    ) -> ExamInfo:
        return ExamInfo(study_description="legacy")

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="placeholder"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text,
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    report_text = """Findings:
Normal finding.
"""

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
        extract_exam_info_fn=legacy_extract_exam_info,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
    )

    assert len(result.extraction.findings) == 1
    assert result.extraction.exam_info.study_description == "placeholder"
    assert any(
        "[stage:extract_exam_info] failed error=TypeError" in message for message in statuses
    )


@pytest.mark.asyncio
async def test_modular_pipeline_exam_info_task_cancelled_on_all_chunk_failure():
    """Exam-info task should be cancelled when all chunk extractions fail."""
    exam_info_completed = False

    async def emit_status(_message: str) -> None:
        return None

    async def always_failing_extract(*, report_text: str, **kwargs):  # noqa: ARG001
        raise RuntimeError("chunk extraction failed")

    async def slow_extract_exam_info(
        report_text: str,  # noqa: ARG001
        *,
        exam_description: str | None = None,  # noqa: ARG001
        source_ref: str | None = None,  # noqa: ARG001
        external_metadata: dict[str, str] | None = None,  # noqa: ARG001
        report_headers: str | None = None,  # noqa: ARG001
    ):
        nonlocal exam_info_completed
        await asyncio.sleep(0.3)
        exam_info_completed = True
        return ExamInfo(study_description="CT Abdomen", modality="CT", body_part="abdomen")

    report_text = """Findings:
Right renal stone.
"""

    with pytest.raises(RuntimeError, match="chunk extraction failed"):
        await run_orchestrated_extraction(
            report_text=report_text,
            exam_description=None,
            model_name="openai:gpt-5-mini",
            reasoning="medium",
            validate=False,
            coding_enabled=False,
            emit_status=emit_status,
            extract_findings_fn=always_failing_extract,
            validate_extraction_fn=_validation_ok,
            extract_exam_info_fn=slow_extract_exam_info,
            max_subagent_concurrency=2,
            unit_repair_attempts=0,
        )

    # Give the event loop a moment to process the cancellation
    await asyncio.sleep(0.05)
    # The exam-info task should have been cancelled, not completed
    assert not exam_info_completed


@pytest.mark.asyncio
async def test_modular_pipeline_validator_review_feedback_threaded_to_retry():
    """Feedback from validator review should be passed to retry units."""
    report_text = """Findings:
finding to review.
"""
    extract_calls = 0
    received_feedback: list[str | None] = []

    async def emit_status(_message: str) -> None:
        return None

    async def fake_extract_findings(*, report_text: str, feedback: str | None = None, **kwargs):  # noqa: ARG001
        nonlocal extract_calls
        extract_calls += 1
        received_feedback.append(feedback)
        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT Abdomen"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text,
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    async def fake_review_chunks(**kwargs):  # noqa: ARG001
        return ValidationReviewDecision(
            reextract_requests=(
                UnitReextractionRequest(
                    label="findings_1",
                    feedback="Look for missed hepatic findings",
                    suspected_issue="missed finding",
                ),
            ),
            rationale="possible missed detail",
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
        review_chunks_fn=fake_review_chunks,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
        validator_reextract_enabled=True,
    )

    assert extract_calls == 2
    # First call has no feedback, second call gets review feedback
    assert received_feedback[0] is None
    assert received_feedback[1] == "Look for missed hepatic findings"
    assert result.pipeline_diagnostics.validator_requested_units == 1
    assert result.pipeline_diagnostics.validator_reextracted_units == 1


@pytest.mark.asyncio
async def test_modular_pipeline_validator_review_timeout_nonfatal():
    """Validator review timeout should be non-fatal — pipeline continues without re-extraction."""
    report_text = """Findings:
Normal finding.
"""
    statuses: list[str] = []

    async def emit_status(message: str) -> None:
        statuses.append(message)

    async def fake_extract_findings(*, report_text: str, **kwargs):  # noqa: ARG001
        finding_text = report_text.splitlines()[-1].strip()
        return ExtractionResult(
            extraction=ReportExtraction(
                exam_info=ExamInfo(study_description="CT"),
                findings=[
                    ExtractedFinding(
                        finding_name=finding_text,
                        presence="present",
                        report_text=finding_text,
                    )
                ],
                non_finding_text=[],
            ),
            usage=None,
        )

    async def slow_review_chunks(**kwargs):  # noqa: ARG001
        await asyncio.sleep(0.5)  # Exceeds timeout
        return ValidationReviewDecision(
            reextract_requests=(UnitReextractionRequest(label="findings_1"),),
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
        review_chunks_fn=slow_review_chunks,
        max_subagent_concurrency=2,
        unit_repair_attempts=0,
        subagent_timeout_seconds=0.05,
    )

    # Pipeline should succeed with the extraction intact
    assert len(result.extraction.findings) == 1
    # Validator review should have failed non-fatally
    assert result.pipeline_diagnostics.validator_requested_units == 0
    assert result.pipeline_diagnostics.validator_reextracted_units == 0
    assert any(
        "validator_review" in msg and "failed" in msg and "TimeoutError" in msg
        for msg in statuses
    )
