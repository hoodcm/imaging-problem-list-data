"""Tests for custom evaluators."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pytest
from pydantic_evals.evaluators import EvaluationReason

from finding_extractor.eval.evaluators import (
    AttributeEvaluator,
    FindingDetectionEvaluator,
    LocationEvaluator,
    NonFindingClassificationEvaluator,
    PresenceClassificationEvaluator,
    VerbatimQuoteEvaluator,
)
from finding_extractor.eval.models import EvalInput
from finding_extractor.models import (
    ExamInfo,
    ExtractedReportFindings,
    Finding,
    FindingAttribute,
    FindingLocation,
    NonFindingText,
    Presence,
)

# ── Test context mock ────────────────────────────────────────────────────────


@dataclass
class FakeEvaluatorContext:
    """Minimal stand-in for pydantic_evals EvaluatorContext used in unit tests."""

    inputs: EvalInput
    output: ExtractedReportFindings
    expected_output: ExtractedReportFindings | None
    metadata: Any = None


# ── Test fixtures ────────────────────────────────────────────────────────────

REPORT_TEXT = """\
The heart size is normal. There is a focal opacity in the right lower lobe.
No pleural effusion. Mild coronary artery calcification."""


def _exam_info() -> ExamInfo:
    return ExamInfo(study_description="Chest XR")


def _make_extraction(
    findings: list[Finding] | None = None,
    non_finding_text: list[NonFindingText] | None = None,
) -> ExtractedReportFindings:
    return ExtractedReportFindings(
        exam_info=_exam_info(),
        findings=findings or [],
        non_finding_text=non_finding_text or [],
    )


BodyRegion = Literal[
    "chest",
    "abdomen",
    "pelvis",
    "head",
    "neck",
    "spine",
    "upper extremity",
    "lower extremity",
    "breast",
]
Laterality = Literal["left", "right", "bilateral"]


def _make_finding(
    name: str = "opacity",
    presence: Presence = "present",
    report_text: str = "There is a focal opacity in the right lower lobe.",
    body_region: BodyRegion = "chest",
    laterality: Laterality | None = "right",
    attributes: list[FindingAttribute] | None = None,
) -> Finding:
    return Finding(
        finding_name=name,
        presence=presence,
        location=FindingLocation(
            body_region=body_region,
            laterality=laterality,
        ),
        attributes=attributes or [],
        report_text=report_text,
    )


def _make_ctx(
    expected: ExtractedReportFindings,
    actual: ExtractedReportFindings,
    report_text: str = REPORT_TEXT,
) -> FakeEvaluatorContext:
    return FakeEvaluatorContext(
        inputs=EvalInput(report_text=report_text),
        output=actual,
        expected_output=expected,
    )


# ── FindingDetectionEvaluator ────────────────────────────────────────────────


class TestFindingDetectionEvaluator:
    def test_perfect_match(self):
        finding = _make_finding()
        expected = _make_extraction(findings=[finding])
        actual = _make_extraction(findings=[finding])
        ctx = _make_ctx(expected, actual)
        result = FindingDetectionEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        assert result["finding_precision"] == 1.0
        assert result["finding_recall"] == 1.0
        f1 = result["finding_f1"]
        assert isinstance(f1, EvaluationReason)
        assert f1.value == 1.0

    def test_no_findings(self):
        expected = _make_extraction(findings=[])
        actual = _make_extraction(findings=[])
        ctx = _make_ctx(expected, actual)
        result = FindingDetectionEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        # Both empty => precision and recall are 1.0 (nothing to detect, nothing missed)
        assert result["finding_precision"] == 1.0
        assert result["finding_recall"] == 1.0

    def test_false_positive(self):
        finding = _make_finding()
        expected = _make_extraction(findings=[])
        actual = _make_extraction(findings=[finding])
        ctx = _make_ctx(expected, actual)
        result = FindingDetectionEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        assert result["finding_precision"] == 0.0
        assert result["finding_recall"] == 1.0  # nothing expected, nothing missed

    def test_false_negative(self):
        finding = _make_finding()
        expected = _make_extraction(findings=[finding])
        actual = _make_extraction(findings=[])
        ctx = _make_ctx(expected, actual)
        result = FindingDetectionEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        assert result["finding_precision"] == 1.0  # nothing produced, nothing wrong
        assert result["finding_recall"] == 0.0

    def test_no_expected_output(self):
        actual = _make_extraction(findings=[_make_finding()])
        ctx = FakeEvaluatorContext(
            inputs=EvalInput(report_text=REPORT_TEXT),
            output=actual,
            expected_output=None,
        )
        result = FindingDetectionEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        assert result["finding_f1"] == 0.0

    def test_reason_present(self):
        finding = _make_finding()
        expected = _make_extraction(findings=[finding])
        actual = _make_extraction(findings=[finding])
        ctx = _make_ctx(expected, actual)
        result = FindingDetectionEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        f1 = result["finding_f1"]
        assert isinstance(f1, EvaluationReason)
        assert f1.reason is not None
        assert "matched" in f1.reason
        assert "FP" in f1.reason
        assert "FN" in f1.reason


# ── PresenceClassificationEvaluator ─────────────────────────────────────────


class TestPresenceClassificationEvaluator:
    def test_correct_presence(self):
        finding = _make_finding(presence="present")
        expected = _make_extraction(findings=[finding])
        actual = _make_extraction(findings=[finding])
        ctx = _make_ctx(expected, actual)
        result = PresenceClassificationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        pa = result["presence_accuracy"]
        assert isinstance(pa, EvaluationReason)
        assert pa.value == 1.0
        assert pa.reason is not None
        assert "1/1 correct" in pa.reason

    def test_wrong_presence(self):
        exp_finding = _make_finding(presence="present")
        act_finding = _make_finding(presence="absent")
        expected = _make_extraction(findings=[exp_finding])
        actual = _make_extraction(findings=[act_finding])
        ctx = _make_ctx(expected, actual)
        result = PresenceClassificationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        pa = result["presence_accuracy"]
        assert isinstance(pa, EvaluationReason)
        assert pa.value == 0.0
        assert pa.reason is not None
        assert "0/1 correct" in pa.reason

    def test_no_matches_empty(self):
        expected = _make_extraction(findings=[])
        actual = _make_extraction(findings=[])
        ctx = _make_ctx(expected, actual)
        result = PresenceClassificationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        assert result["presence_accuracy"] == 1.0


# ── LocationEvaluator ────────────────────────────────────────────────────────


class TestLocationEvaluator:
    def test_correct_location(self):
        finding = _make_finding(body_region="chest", laterality="right")
        expected = _make_extraction(findings=[finding])
        actual = _make_extraction(findings=[finding])
        ctx = _make_ctx(expected, actual)
        result = LocationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        br = result["body_region_accuracy"]
        assert isinstance(br, EvaluationReason)
        assert br.value == 1.0
        assert br.reason is not None
        assert "1/1 correct" in br.reason
        lat = result["laterality_accuracy"]
        assert isinstance(lat, EvaluationReason)
        assert lat.value == 1.0
        assert lat.reason is not None
        assert "1/1 correct" in lat.reason

    def test_wrong_body_region(self):
        exp = _make_finding(body_region="chest")
        act = _make_finding(body_region="abdomen")
        expected = _make_extraction(findings=[exp])
        actual = _make_extraction(findings=[act])
        ctx = _make_ctx(expected, actual)
        result = LocationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        br = result["body_region_accuracy"]
        assert isinstance(br, EvaluationReason)
        assert br.value == 0.0
        assert br.reason is not None
        assert "0/1 correct" in br.reason

    def test_wrong_laterality(self):
        exp = _make_finding(laterality="right")
        act = _make_finding(laterality="left")
        expected = _make_extraction(findings=[exp])
        actual = _make_extraction(findings=[act])
        ctx = _make_ctx(expected, actual)
        result = LocationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        lat = result["laterality_accuracy"]
        assert isinstance(lat, EvaluationReason)
        assert lat.value == 0.0
        assert lat.reason is not None
        assert "0/1 correct" in lat.reason

    def test_no_laterality_expected(self):
        exp = _make_finding(laterality=None)
        act = _make_finding(laterality="right")
        expected = _make_extraction(findings=[exp])
        actual = _make_extraction(findings=[act])
        ctx = _make_ctx(expected, actual)
        result = LocationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        # No laterality expected => laterality_accuracy defaults to 1.0
        lat = result["laterality_accuracy"]
        assert isinstance(lat, EvaluationReason)
        assert lat.value == 1.0
        assert lat.reason is not None
        assert "no laterality to evaluate" in lat.reason


# ── AttributeEvaluator ──────────────────────────────────────────────────────


class TestAttributeEvaluator:
    def test_matching_attributes(self):
        attrs = [FindingAttribute(key="size", value="3 mm")]
        finding = _make_finding(attributes=attrs)
        expected = _make_extraction(findings=[finding])
        actual = _make_extraction(findings=[finding])
        ctx = _make_ctx(expected, actual)
        result = AttributeEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        prec = result["attribute_precision"]
        assert isinstance(prec, EvaluationReason)
        assert prec.value == 1.0
        assert prec.reason is not None
        assert "1/1 matched" in prec.reason
        rec = result["attribute_recall"]
        assert isinstance(rec, EvaluationReason)
        assert rec.value == 1.0
        assert rec.reason is not None
        assert "1/1 matched" in rec.reason

    def test_extra_attribute(self):
        exp_finding = _make_finding(attributes=[FindingAttribute(key="size", value="3 mm")])
        act_finding = _make_finding(
            attributes=[
                FindingAttribute(key="size", value="3 mm"),
                FindingAttribute(key="severity", value="mild"),
            ]
        )
        expected = _make_extraction(findings=[exp_finding])
        actual = _make_extraction(findings=[act_finding])
        ctx = _make_ctx(expected, actual)
        result = AttributeEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        prec = result["attribute_precision"]
        assert isinstance(prec, EvaluationReason)
        assert prec.value == 0.5  # 1 matched / 2 actual
        assert prec.reason is not None
        assert "1/2 matched" in prec.reason
        rec = result["attribute_recall"]
        assert isinstance(rec, EvaluationReason)
        assert rec.value == 1.0  # 1 matched / 1 expected

    def test_missing_attribute(self):
        exp_finding = _make_finding(
            attributes=[
                FindingAttribute(key="size", value="3 mm"),
                FindingAttribute(key="severity", value="mild"),
            ]
        )
        act_finding = _make_finding(attributes=[FindingAttribute(key="size", value="3 mm")])
        expected = _make_extraction(findings=[exp_finding])
        actual = _make_extraction(findings=[act_finding])
        ctx = _make_ctx(expected, actual)
        result = AttributeEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        prec = result["attribute_precision"]
        assert isinstance(prec, EvaluationReason)
        assert prec.value == 1.0  # 1 matched / 1 actual
        rec = result["attribute_recall"]
        assert isinstance(rec, EvaluationReason)
        assert rec.value == 0.5  # 1 matched / 2 expected
        assert rec.reason is not None
        assert "1/2 matched" in rec.reason

    def test_no_attributes(self):
        finding = _make_finding(attributes=[])
        expected = _make_extraction(findings=[finding])
        actual = _make_extraction(findings=[finding])
        ctx = _make_ctx(expected, actual)
        result = AttributeEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        prec = result["attribute_precision"]
        assert isinstance(prec, EvaluationReason)
        assert prec.value == 1.0
        assert prec.reason is not None
        assert "no actual attributes" in prec.reason
        rec = result["attribute_recall"]
        assert isinstance(rec, EvaluationReason)
        assert rec.value == 1.0
        assert rec.reason is not None
        assert "no expected attributes" in rec.reason


# ── VerbatimQuoteEvaluator ──────────────────────────────────────────────────


class TestVerbatimQuoteEvaluator:
    def test_verbatim_pass(self):
        finding = _make_finding(report_text="There is a focal opacity in the right lower lobe.")
        actual = _make_extraction(findings=[finding])
        ctx = FakeEvaluatorContext(
            inputs=EvalInput(report_text=REPORT_TEXT),
            output=actual,
            expected_output=None,
        )
        result = VerbatimQuoteEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        vp = result["verbatim_pass"]
        assert isinstance(vp, EvaluationReason)
        assert vp.value is True
        assert result["verbatim_rate"] == 1.0

    def test_verbatim_fail(self):
        finding = _make_finding(report_text="This text does not appear in the report at all.")
        actual = _make_extraction(findings=[finding])
        ctx = FakeEvaluatorContext(
            inputs=EvalInput(report_text=REPORT_TEXT),
            output=actual,
            expected_output=None,
        )
        result = VerbatimQuoteEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        vp = result["verbatim_pass"]
        assert isinstance(vp, EvaluationReason)
        assert vp.value is False
        assert result["verbatim_rate"] == 0.0

    def test_empty_extraction(self):
        actual = _make_extraction(findings=[], non_finding_text=[])
        ctx = FakeEvaluatorContext(
            inputs=EvalInput(report_text=REPORT_TEXT),
            output=actual,
            expected_output=None,
        )
        result = VerbatimQuoteEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        vp = result["verbatim_pass"]
        assert isinstance(vp, EvaluationReason)
        assert vp.value is True
        assert result["verbatim_rate"] == 1.0

    def test_partial_verbatim(self):
        good = _make_finding(report_text="There is a focal opacity in the right lower lobe.")
        bad = _make_finding(
            name="pleural effusion",
            report_text="This text is not in the report.",
        )
        actual = _make_extraction(findings=[good, bad])
        ctx = FakeEvaluatorContext(
            inputs=EvalInput(report_text=REPORT_TEXT),
            output=actual,
            expected_output=None,
        )
        result = VerbatimQuoteEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        vp = result["verbatim_pass"]
        assert isinstance(vp, EvaluationReason)
        assert vp.value is False
        assert result["verbatim_rate"] == 0.5

    def test_verbatim_reason_on_pass(self):
        finding = _make_finding(report_text="There is a focal opacity in the right lower lobe.")
        actual = _make_extraction(findings=[finding])
        ctx = FakeEvaluatorContext(
            inputs=EvalInput(report_text=REPORT_TEXT),
            output=actual,
            expected_output=None,
        )
        result = VerbatimQuoteEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        vp = result["verbatim_pass"]
        assert isinstance(vp, EvaluationReason)
        assert vp.reason is not None
        assert "1/1 verbatim" in vp.reason

    def test_verbatim_reason_on_fail(self):
        bad = _make_finding(report_text="This text is not in the report.")
        actual = _make_extraction(findings=[bad])
        ctx = FakeEvaluatorContext(
            inputs=EvalInput(report_text=REPORT_TEXT),
            output=actual,
            expected_output=None,
        )
        result = VerbatimQuoteEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        vp = result["verbatim_pass"]
        assert isinstance(vp, EvaluationReason)
        assert vp.reason is not None
        assert "not verbatim" in vp.reason


# ── NonFindingClassificationEvaluator ────────────────────────────────────────


class TestNonFindingClassificationEvaluator:
    def test_correct_classification(self):
        nft = NonFindingText(text="Technique: Frontal and lateral views.", category="technique")
        expected = _make_extraction(non_finding_text=[nft])
        actual = _make_extraction(non_finding_text=[nft])
        ctx = _make_ctx(expected, actual)
        result = NonFindingClassificationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        assert result["nonfinding_category_accuracy"] == 1.0

    def test_wrong_classification(self):
        exp_nft = NonFindingText(text="Technique: Frontal and lateral views.", category="technique")
        act_nft = NonFindingText(
            text="Technique: Frontal and lateral views.", category="indication"
        )
        expected = _make_extraction(non_finding_text=[exp_nft])
        actual = _make_extraction(non_finding_text=[act_nft])
        ctx = _make_ctx(expected, actual)
        result = NonFindingClassificationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        assert result["nonfinding_category_accuracy"] == 0.0

    def test_no_non_finding_text(self):
        expected = _make_extraction(non_finding_text=[])
        actual = _make_extraction(non_finding_text=[])
        ctx = _make_ctx(expected, actual)
        result = NonFindingClassificationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        assert result["nonfinding_category_accuracy"] == 1.0

    def test_no_expected_output(self):
        actual = _make_extraction()
        ctx = FakeEvaluatorContext(
            inputs=EvalInput(report_text=REPORT_TEXT),
            output=actual,
            expected_output=None,
        )
        result = NonFindingClassificationEvaluator().evaluate(ctx)  # type: ignore[arg-type]
        assert result["nonfinding_category_accuracy"] == 0.0


# ── Integration with examples ────────────────────────────────────────────────


class TestEvaluatorsWithExamples:
    """Test evaluators against the CT abdomen example (expected == actual)."""

    @pytest.fixture
    def ct_ctx(self) -> FakeEvaluatorContext:
        from finding_extractor.examples import get_ct_abdomen_example

        report_text, extraction = get_ct_abdomen_example()
        return FakeEvaluatorContext(
            inputs=EvalInput(report_text=report_text),
            output=extraction,
            expected_output=extraction,
        )

    def test_perfect_detection(self, ct_ctx):
        result = FindingDetectionEvaluator().evaluate(ct_ctx)
        f1 = result["finding_f1"]
        assert isinstance(f1, EvaluationReason)
        assert f1.value == 1.0

    def test_perfect_presence(self, ct_ctx):
        result = PresenceClassificationEvaluator().evaluate(ct_ctx)
        pa = result["presence_accuracy"]
        assert isinstance(pa, EvaluationReason)
        assert pa.value == 1.0

    def test_perfect_location(self, ct_ctx):
        result = LocationEvaluator().evaluate(ct_ctx)
        br = result["body_region_accuracy"]
        assert isinstance(br, EvaluationReason)
        assert br.value == 1.0
        lat = result["laterality_accuracy"]
        assert isinstance(lat, EvaluationReason)
        assert lat.value == 1.0

    def test_perfect_attributes(self, ct_ctx):
        result = AttributeEvaluator().evaluate(ct_ctx)
        prec = result["attribute_precision"]
        assert isinstance(prec, EvaluationReason)
        assert prec.value == 1.0
        rec = result["attribute_recall"]
        assert isinstance(rec, EvaluationReason)
        assert rec.value == 1.0

    def test_perfect_verbatim(self, ct_ctx):
        result = VerbatimQuoteEvaluator().evaluate(ct_ctx)
        vp = result["verbatim_pass"]
        assert isinstance(vp, EvaluationReason)
        assert vp.value is True

    def test_perfect_nonfinding(self, ct_ctx):
        result = NonFindingClassificationEvaluator().evaluate(ct_ctx)
        assert result["nonfinding_category_accuracy"] == 1.0
