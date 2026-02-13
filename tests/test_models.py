"""Tests for finding extractor models."""

from datetime import date
from typing import Any, cast

import pytest
from pydantic import ValidationError

from finding_extractor.models import (
    ExamInfo,
    ExtractedFinding,
    FindingAttribute,
    FindingLocation,
    NonFindingText,
    ReportExtraction,
    ValidationResult,
)


class TestExamInfo:
    """Test cases for ExamInfo model."""

    def test_basic_creation(self):
        """Test creating ExamInfo with minimal fields."""
        info = ExamInfo(study_description="CT Abdomen and Pelvis WO contrast")
        assert info.study_description == "CT Abdomen and Pelvis WO contrast"
        assert info.study_date is None
        assert info.modality is None
        assert info.body_part is None

    def test_full_creation(self):
        """Test creating ExamInfo with all fields."""
        info = ExamInfo(
            study_description="CT Abdomen and Pelvis WO contrast",
            study_date=cast(Any, "2021-08-26"),
            modality="CT",
            body_part="abdomen",
        )
        assert info.study_description == "CT Abdomen and Pelvis WO contrast"
        assert info.study_date == date(2021, 8, 26)
        assert info.modality == "CT"
        assert info.body_part == "abdomen"


class TestFindingLocation:
    """Test cases for FindingLocation model."""

    def test_basic_creation(self):
        """Test creating FindingLocation with just body_region."""
        loc = FindingLocation(body_region="abdomen")
        assert loc.body_region == "abdomen"
        assert loc.specific_anatomy is None
        assert loc.laterality is None

    def test_full_creation(self):
        """Test creating FindingLocation with all fields."""
        loc = FindingLocation(
            body_region="abdomen",
            specific_anatomy="right lower pole",
            laterality="right",
        )
        assert loc.body_region == "abdomen"
        assert loc.specific_anatomy == "right lower pole"
        assert loc.laterality == "right"


class TestFindingAttribute:
    """Test cases for FindingAttribute model."""

    def test_creation(self):
        """Test creating FindingAttribute."""
        attr = FindingAttribute(key="size", value="3 mm")
        assert attr.key == "size"
        assert attr.value == "3 mm"


class TestExtractedFinding:
    """Test cases for ExtractedFinding model."""

    def test_basic_creation(self):
        """Test creating ExtractedFinding with minimal fields."""
        finding = ExtractedFinding(
            finding_name="renal calculus",
            presence="present",
            report_text="Stone seen in right kidney.",
        )
        assert finding.finding_name == "renal calculus"
        assert finding.presence == "present"
        assert finding.location is None
        assert finding.attributes == []
        assert finding.report_text == "Stone seen in right kidney."

    def test_full_creation(self):
        """Test creating ExtractedFinding with all fields."""
        finding = ExtractedFinding(
            finding_name="renal calculus",
            presence="present",
            location=FindingLocation(
                body_region="abdomen",
                specific_anatomy="right lower pole",
                laterality="right",
            ),
            attributes=[
                FindingAttribute(key="size", value="3 mm"),
                FindingAttribute(key="morphology", value="nonobstructing"),
            ],
            report_text="Stone seen in right kidney lower pole.",
        )
        assert finding.finding_name == "renal calculus"
        assert finding.presence == "present"
        assert finding.location is not None
        assert finding.location.body_region == "abdomen"
        assert len(finding.attributes) == 2
        assert finding.report_text == "Stone seen in right kidney lower pole."

    def test_valid_presence_values(self):
        """Test that only valid presence values are accepted."""
        for presence in ["present", "absent", "indeterminate", "possible"]:
            finding = ExtractedFinding(
                finding_name="test",
                presence=presence,  # type: ignore[arg-type]
                report_text="test",
            )
            assert finding.presence == presence

    def test_source_section_default_none(self):
        """source_section defaults to None when not provided."""
        finding = ExtractedFinding(
            finding_name="test",
            presence="present",
            report_text="test",
        )
        assert finding.source_section is None

    def test_source_section_valid_values(self):
        """source_section accepts all valid literal values."""
        for section in ["findings", "impression", "both"]:
            finding = ExtractedFinding(
                finding_name="test",
                presence="present",
                report_text="test",
                source_section=section,  # type: ignore[arg-type]
            )
            assert finding.source_section == section

    def test_source_section_invalid_value_rejected(self):
        """Invalid source_section values are rejected."""
        with pytest.raises(ValidationError):
            ExtractedFinding(
                finding_name="test",
                presence="present",
                report_text="test",
                source_section=cast(Any, "technique"),
            )


class TestNonFindingText:
    """Test cases for NonFindingText model."""

    def test_creation(self):
        """Test creating NonFindingText."""
        nft = NonFindingText(
            text="Technique: CT of the abdomen",
            category="technique",
        )
        assert nft.text == "Technique: CT of the abdomen"
        assert nft.category == "technique"


class TestReportExtraction:
    """Test cases for ReportExtraction model."""

    def test_basic_creation(self):
        """Test creating ReportExtraction with minimal fields."""
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="CT Abdomen"),
        )
        assert extraction.exam_info.study_description == "CT Abdomen"
        assert extraction.findings == []
        assert extraction.non_finding_text == []

    def test_full_creation(self):
        """Test creating ReportExtraction with all fields."""
        extraction = ReportExtraction(
            exam_info=ExamInfo(
                study_description="CT Abdomen and Pelvis WO contrast",
                study_date=cast(Any, "2021-08-26"),
                modality="CT",
                body_part="abdomen",
            ),
            findings=[
                ExtractedFinding(
                    finding_name="renal calculus",
                    presence="present",
                    report_text="Stone seen.",
                ),
            ],
            non_finding_text=[
                NonFindingText(
                    text="Technique: CT",
                    category="technique",
                ),
            ],
        )
        assert len(extraction.findings) == 1
        assert len(extraction.non_finding_text) == 1

    def test_serialization(self):
        """Test that ReportExtraction can be serialized to dict/JSON."""
        extraction = ReportExtraction(
            exam_info=ExamInfo(study_description="CT Abdomen"),
            findings=[
                ExtractedFinding(
                    finding_name="test finding",
                    presence="present",
                    report_text="Test text.",
                ),
            ],
        )
        data = extraction.model_dump()
        assert "exam_info" in data
        assert "findings" in data
        assert "non_finding_text" in data
        assert len(data["findings"]) == 1


class TestValidationResult:
    """Test cases for ValidationResult model."""

    def test_valid_result(self):
        """Test creating a valid ValidationResult."""
        result = ValidationResult(is_valid=True)
        assert result.is_valid is True
        assert result.verbatim_errors == []
        assert result.coverage_warnings == []

    def test_invalid_result(self):
        """Test creating an invalid ValidationResult with errors."""
        result = ValidationResult(
            is_valid=False,
            verbatim_errors=["Error 1", "Error 2"],
            coverage_warnings=["Warning 1"],
        )
        assert result.is_valid is False
        assert len(result.verbatim_errors) == 2
        assert len(result.coverage_warnings) == 1


class TestSchemaStrictness:
    """Test cases for Literal type and extra='forbid' enforcement."""

    def test_invalid_category_rejected(self):
        """Test that an invalid NonFindingText category is rejected."""
        with pytest.raises(ValidationError):
            NonFindingText(text="x", category=cast(Any, "invalid"))

    def test_invalid_body_region_rejected(self):
        """Test that an invalid body_region is rejected."""
        with pytest.raises(ValidationError):
            FindingLocation(body_region=cast(Any, "invalid"))

    def test_invalid_laterality_rejected(self):
        """Test that an invalid laterality is rejected."""
        with pytest.raises(ValidationError):
            FindingLocation(body_region="chest", laterality=cast(Any, "middle"))

    def test_extra_fields_rejected(self):
        """Test that extra fields are rejected due to extra='forbid'."""
        with pytest.raises(ValidationError):
            ExamInfo.model_validate({"study_description": "CT", "unknown_field": "x"})

    def test_impression_category_accepted(self):
        """Test that 'impression' is a valid NonFindingText category."""
        nft = NonFindingText(text="x", category="impression")
        assert nft.category == "impression"

    def test_spine_body_region_accepted(self):
        """Test that 'spine' is a valid body_region."""
        loc = FindingLocation(body_region="spine")
        assert loc.body_region == "spine"


class TestDateHandling:
    """Test cases for study_date date type handling."""

    def test_study_date_accepts_date_object(self):
        """Test that study_date accepts a date object."""
        info = ExamInfo(study_description="CT", study_date=date(2021, 8, 26))
        assert info.study_date == date(2021, 8, 26)

    def test_study_date_accepts_iso_string(self):
        """Test that study_date accepts an ISO date string (Pydantic coercion)."""
        info = ExamInfo(study_description="CT", study_date=cast(Any, "2021-08-26"))
        assert info.study_date == date(2021, 8, 26)

    def test_study_date_serializes_to_iso(self):
        """Test that study_date serializes correctly."""
        info = ExamInfo(study_description="CT", study_date=date(2021, 8, 26))
        # Default mode returns date object
        assert info.model_dump()["study_date"] == date(2021, 8, 26)
        # JSON mode returns ISO string
        assert info.model_dump(mode="json")["study_date"] == "2021-08-26"
