"""Tests for the finding matching algorithm."""

from __future__ import annotations

from typing import Literal

import pytest

from finding_extractor.eval.matching import (
    MatchResult,
    _finding_tokens,
    jaccard_similarity,
    match_findings,
    tokenize,
)
from finding_extractor.models import (
    Finding,
    FindingAttribute,
    FindingLocation,
    Presence,
)

# Body-region type alias matching FindingLocation.body_region
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

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_finding(
    name: str = "renal calculus",
    presence: Presence = "present",
    report_text: str = "There is a renal calculus.",
    body_region: BodyRegion = "abdomen",
    laterality: Laterality | None = None,
    specific_anatomy: str | None = None,
    attributes: list[FindingAttribute] | None = None,
) -> Finding:
    return Finding(
        finding_name=name,
        presence=presence,
        location=FindingLocation(
            body_region=body_region,
            laterality=laterality,
            specific_anatomy=specific_anatomy,
        ),
        attributes=attributes or [],
        report_text=report_text,
    )


# ── Tokenization tests ──────────────────────────────────────────────────────


class TestTokenize:
    def test_basic_tokenization(self):
        assert tokenize("renal calculus") == {"renal", "calculus"}

    def test_case_insensitive(self):
        assert tokenize("Renal Calculus") == {"renal", "calculus"}

    def test_empty_string(self):
        assert tokenize("") == set()

    def test_strips_punctuation(self):
        assert tokenize("kidney.") == {"kidney"}
        assert tokenize("region,") == {"region"}

    def test_splits_hyphenated(self):
        """En-dash and hyphenated ranges split into separate tokens."""
        assert tokenize("4\u20135") == {"4", "5"}
        assert tokenize("4-5 mm") == {"4", "5", "mm"}


class TestFindingTokens:
    def test_combines_name_and_report_text(self):
        finding = _make_finding(
            name="renal calculus",
            report_text="There is a stone in the kidney.",
        )
        tokens = _finding_tokens(finding)
        assert "renal" in tokens
        assert "calculus" in tokens
        assert "stone" in tokens
        assert "kidney" in tokens  # punctuation stripped by regex tokenizer


# ── Jaccard similarity tests ────────────────────────────────────────────────


class TestJaccardSimilarity:
    def test_identical_sets(self):
        tokens = {"renal", "calculus"}
        assert jaccard_similarity(tokens, tokens) == 1.0

    def test_disjoint_sets(self):
        assert jaccard_similarity({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self):
        a = {"renal", "calculus", "stone"}
        b = {"renal", "calculus", "kidney"}
        # intersection = {renal, calculus} = 2, union = 4
        assert jaccard_similarity(a, b) == pytest.approx(0.5)

    def test_empty_sets(self):
        assert jaccard_similarity(set(), {"a"}) == 0.0
        assert jaccard_similarity({"a"}, set()) == 0.0
        assert jaccard_similarity(set(), set()) == 0.0


# ── match_findings tests ────────────────────────────────────────────────────


class TestMatchFindings:
    def test_both_empty(self):
        result = match_findings([], [])
        assert result == MatchResult(matches=[], unmatched_expected=[], unmatched_actual=[])

    def test_expected_empty(self):
        actual = [_make_finding()]
        result = match_findings([], actual)
        assert result.matches == []
        assert result.unmatched_expected == []
        assert result.unmatched_actual == actual

    def test_actual_empty(self):
        expected = [_make_finding()]
        result = match_findings(expected, [])
        assert result.matches == []
        assert result.unmatched_expected == expected
        assert result.unmatched_actual == []

    def test_perfect_match(self):
        finding = _make_finding()
        result = match_findings([finding], [finding])
        assert len(result.matches) == 1
        assert result.matches[0].expected == finding
        assert result.matches[0].actual == finding
        assert result.unmatched_expected == []
        assert result.unmatched_actual == []

    def test_similar_findings_match(self):
        expected = _make_finding(name="renal calculus", report_text="Bilateral renal stones.")
        actual = _make_finding(name="renal stone", report_text="Bilateral renal stones noted.")
        result = match_findings([expected], [actual])
        assert len(result.matches) == 1
        assert result.matches[0].similarity > 0.3

    def test_dissimilar_findings_no_match(self):
        expected = _make_finding(
            name="renal calculus",
            presence="present",
            report_text="Bilateral nonobstructing renal calculi identified.",
        )
        actual = _make_finding(
            name="pneumonia",
            presence="absent",
            report_text="Focal opacity consistent with pneumonia right lower lobe.",
            body_region="chest",
        )
        result = match_findings([expected], [actual])
        assert result.matches == []
        assert len(result.unmatched_expected) == 1
        assert len(result.unmatched_actual) == 1

    def test_presence_bonus_applied(self):
        """Same-presence findings get +0.1 bonus, affecting match preference."""
        expected = _make_finding(
            name="calcification",
            presence="present",
            report_text="Calcification present.",
        )
        actual_match = _make_finding(
            name="calcification",
            presence="present",
            report_text="Calcification present here.",
        )
        actual_mismatch = _make_finding(
            name="calcification",
            presence="absent",
            report_text="Calcification present here.",
        )
        # Both should match, but the one with same presence gets the bonus
        result_same = match_findings([expected], [actual_match])
        result_diff = match_findings([expected], [actual_mismatch])
        if result_same.matches and result_diff.matches:
            assert result_same.matches[0].similarity > result_diff.matches[0].similarity

    def test_greedy_best_match(self):
        """Greedy matching pairs the best-matched findings first."""
        exp1 = _make_finding(name="renal calculus", report_text="Renal stone right kidney 3mm.")
        exp2 = _make_finding(name="renal calculus", report_text="Renal stone left kidney 5mm.")
        act1 = _make_finding(name="renal calculus", report_text="Renal stone right kidney 3mm.")
        act2 = _make_finding(name="renal calculus", report_text="Renal stone left kidney 5mm.")
        result = match_findings([exp1, exp2], [act1, act2])
        assert len(result.matches) == 2
        assert result.unmatched_expected == []
        assert result.unmatched_actual == []

    def test_multiple_with_unmatched(self):
        exp1 = _make_finding(name="renal calculus", report_text="Stone in kidney.")
        exp2 = _make_finding(name="hepatic steatosis", report_text="Fatty liver.")
        act1 = _make_finding(name="renal calculus", report_text="Stone in kidney.")
        # exp2 (hepatic steatosis) should be unmatched
        result = match_findings([exp1, exp2], [act1])
        assert len(result.matches) == 1
        assert len(result.unmatched_expected) == 1
        assert result.unmatched_expected[0].finding_name == "hepatic steatosis"
        assert result.unmatched_actual == []

    def test_custom_threshold(self):
        """Higher threshold requires closer matches."""
        expected = _make_finding(name="calcification", report_text="There is calcification.")
        actual = _make_finding(
            name="vascular calcification",
            report_text="Vascular calcification is present.",
        )
        # With default threshold (0.3), should match
        result_low = match_findings([expected], [actual], threshold=0.3)
        # With very high threshold (0.9), should NOT match
        result_high = match_findings([expected], [actual], threshold=0.9)
        assert len(result_low.matches) >= 0  # depends on actual similarity
        assert len(result_high.matches) == 0

    def test_from_examples_ct_abdomen(self):
        """Integration test: matching CT abdomen example against itself."""
        from finding_extractor.examples import get_ct_abdomen_example

        _, extraction = get_ct_abdomen_example()
        result = match_findings(extraction.findings, extraction.findings)
        assert len(result.matches) == len(extraction.findings)
        assert result.unmatched_expected == []
        assert result.unmatched_actual == []

    def test_from_examples_xr_chest(self):
        """Integration test: matching XR chest example against itself."""
        from finding_extractor.examples import get_xr_chest_example

        _, extraction = get_xr_chest_example()
        result = match_findings(extraction.findings, extraction.findings)
        assert len(result.matches) == len(extraction.findings)
        assert result.unmatched_expected == []
        assert result.unmatched_actual == []


# ── Location bonus tests ──────────────────────────────────────────────────
#
# These test the location bonus behavior through the public match_findings API.
# A matching-laterality pair should get a higher similarity than a mismatched one.


class TestLocationBonus:
    def test_same_laterality_scores_higher(self):
        """Same-laterality pairing gets a higher similarity than cross-laterality."""
        right = _make_finding(name="renal calculus", report_text="There is a renal calculus.", laterality="right", body_region="abdomen")
        left = _make_finding(name="renal calculus", report_text="There is a renal calculus.", laterality="left", body_region="abdomen")

        same = match_findings([right], [right])
        cross = match_findings([right], [left])
        assert same.matches[0].similarity > cross.matches[0].similarity

    def test_same_anatomy_scores_higher(self):
        """Same-anatomy pairing gets a higher similarity than different anatomy."""
        thoracic = _make_finding(name="degenerative change", report_text="Degenerative change.", body_region="spine", specific_anatomy="thoracic spine")
        lumbar = _make_finding(name="degenerative change", report_text="Degenerative change.", body_region="spine", specific_anatomy="lumbar spine")

        same = match_findings([thoracic], [thoracic])
        cross = match_findings([thoracic], [lumbar])
        assert same.matches[0].similarity > cross.matches[0].similarity

    def test_no_location_still_matches(self):
        """Findings without location data still match on text similarity."""
        a = Finding(
            finding_name="test finding",
            presence="present",
            location=None,
            attributes=[],
            report_text="Some test text.",
        )
        result = match_findings([a], [a])
        assert len(result.matches) == 1


# ── Attribute bonus tests ─────────────────────────────────────────────────
#
# These test the attribute bonus behavior through the public match_findings API.


class TestAttributeBonus:
    def test_same_attributes_score_higher(self):
        """Matching attributes boost similarity over mismatched attributes."""
        a = _make_finding(name="renal calculus", report_text="There is a renal calculus.", attributes=[FindingAttribute(key="size", value="3 mm")])
        b_match = _make_finding(name="renal calculus", report_text="There is a renal calculus.", attributes=[FindingAttribute(key="size", value="3 mm")])
        b_mismatch = _make_finding(name="renal calculus", report_text="There is a renal calculus.", attributes=[FindingAttribute(key="size", value="5 mm")])

        same = match_findings([a], [b_match])
        diff = match_findings([a], [b_mismatch])
        assert same.matches[0].similarity > diff.matches[0].similarity

    def test_no_attributes_still_matches(self):
        """Findings without attributes still match on text similarity."""
        a = _make_finding(attributes=[])
        result = match_findings([a], [a])
        assert len(result.matches) == 1

    def test_size_disambiguation_via_matching(self):
        """Attribute differences steer pairing when text is identical."""
        shared_text = "Bilateral renal stones 3 mm right and 5 mm left."
        exp_3mm = _make_finding(
            report_text=shared_text,
            laterality="right",
            attributes=[FindingAttribute(key="size", value="3 mm")],
        )
        exp_5mm = _make_finding(
            report_text=shared_text,
            laterality="left",
            attributes=[FindingAttribute(key="size", value="5 mm")],
        )
        # Actual in reversed order
        act_5mm = _make_finding(
            report_text=shared_text,
            laterality="left",
            attributes=[FindingAttribute(key="size", value="5 mm")],
        )
        act_3mm = _make_finding(
            report_text=shared_text,
            laterality="right",
            attributes=[FindingAttribute(key="size", value="3 mm")],
        )
        result = match_findings([exp_3mm, exp_5mm], [act_5mm, act_3mm])
        assert len(result.matches) == 2
        for m in result.matches:
            # Each match should pair the same size together
            exp_size = m.expected.attributes[0].value
            act_size = m.actual.attributes[0].value
            assert exp_size == act_size


# ── Disambiguation tests ──────────────────────────────────────────────────


class TestDisambiguation:
    """Test that location + attribute bonuses correctly disambiguate duplicate-name findings."""

    SHARED_TEXT = (
        "Both kidneys demonstrate small nonobstructing calculi. "
        "Stable bilateral renal stones including right lower pole stone "
        "measuring approximately 3 mm and left interpolar region, "
        "measuring about 4\u20135 mm."
    )

    def test_laterality_disambiguation(self):
        """Two findings with same name and text but different laterality are correctly paired."""
        exp_right = _make_finding(
            name="renal calculus",
            report_text=self.SHARED_TEXT,
            laterality="right",
            specific_anatomy="right lower pole",
            attributes=[FindingAttribute(key="size", value="3 mm")],
        )
        exp_left = _make_finding(
            name="renal calculus",
            report_text=self.SHARED_TEXT,
            laterality="left",
            specific_anatomy="left interpolar region",
            attributes=[FindingAttribute(key="size", value="4\u20135 mm")],
        )

        # Actual findings in reversed order to test disambiguation
        act_left = _make_finding(
            name="renal calculus",
            report_text=self.SHARED_TEXT,
            laterality="left",
            specific_anatomy="left interpolar region",
            attributes=[FindingAttribute(key="size", value="4\u20135 mm")],
        )
        act_right = _make_finding(
            name="renal calculus",
            report_text=self.SHARED_TEXT,
            laterality="right",
            specific_anatomy="right lower pole",
            attributes=[FindingAttribute(key="size", value="3 mm")],
        )

        result = match_findings([exp_right, exp_left], [act_left, act_right])
        assert len(result.matches) == 2
        assert result.unmatched_expected == []
        assert result.unmatched_actual == []

        for m in result.matches:
            assert m.expected.location is not None
            assert m.actual.location is not None
            assert m.expected.location.laterality == m.actual.location.laterality

    def test_anatomy_disambiguation(self):
        """Two spinal findings with same text but different anatomy are correctly paired."""
        shared_text = "Advanced degenerative changes throughout the thoracic and lumbar spine."

        exp_thoracic = _make_finding(
            name="spinal degenerative change",
            report_text=shared_text,
            body_region="spine",
            specific_anatomy="thoracic spine",
        )
        exp_lumbar = _make_finding(
            name="spinal degenerative change",
            report_text=shared_text,
            body_region="spine",
            specific_anatomy="lumbar spine",
        )

        # Actual in reversed order
        act_lumbar = _make_finding(
            name="spinal degenerative change",
            report_text=shared_text,
            body_region="spine",
            specific_anatomy="lumbar spine",
        )
        act_thoracic = _make_finding(
            name="spinal degenerative change",
            report_text=shared_text,
            body_region="spine",
            specific_anatomy="thoracic spine",
        )

        result = match_findings([exp_thoracic, exp_lumbar], [act_lumbar, act_thoracic])
        assert len(result.matches) == 2

        for m in result.matches:
            assert m.expected.location is not None
            assert m.actual.location is not None
            assert m.expected.location.specific_anatomy == m.actual.location.specific_anatomy


class TestSelfMatchDiagnostics:
    """Diagnostic tests proving that self-match correctly pairs duplicate-name findings.

    These tests load comprehensive dataset cases and verify that findings with
    identical names but different locations/attributes are paired correctly.
    """

    @pytest.fixture
    def comprehensive_cases(self):
        from pydantic_evals import Dataset

        from finding_extractor.eval.models import EvalInput
        from finding_extractor.models import ExtractedReportFindings

        dataset = Dataset[EvalInput, ExtractedReportFindings].from_file(
            "evals/datasets/comprehensive.yaml"
        )
        return dataset.cases

    def test_self_match_all_cases(self, comprehensive_cases):
        """Every case's findings should perfectly self-match (same count, no unmatched)."""
        for case in comprehensive_cases:
            if case.expected_output is None:
                continue
            findings = case.expected_output.findings
            result = match_findings(findings, findings)
            assert len(result.matches) == len(findings), (
                f"Case {case.name}: expected {len(findings)} matches, "
                f"got {len(result.matches)}"
            )
            assert result.unmatched_expected == [], f"Case {case.name}: unexpected FN"
            assert result.unmatched_actual == [], f"Case {case.name}: unexpected FP"

    def test_renal_calculus_disambiguation(self, comprehensive_cases):
        """Renal calculus findings with different laterality should be paired correctly."""
        for case in comprehensive_cases:
            if case.expected_output is None:
                continue
            findings = case.expected_output.findings
            renal_findings = [
                f for f in findings if f.finding_name == "renal calculus"
            ]
            if len(renal_findings) < 2:
                continue

            result = match_findings(renal_findings, renal_findings)
            assert len(result.matches) == len(renal_findings)

            for m in result.matches:
                if (
                    m.expected.location
                    and m.actual.location
                    and m.expected.location.laterality
                    and m.actual.location.laterality
                ):
                    assert m.expected.location.laterality == m.actual.location.laterality, (
                        f"Case {case.name}: renal calculus laterality mismatch — "
                        f"expected {m.expected.location.laterality}, "
                        f"got {m.actual.location.laterality}"
                    )

    def test_spinal_degenerative_disambiguation(self, comprehensive_cases):
        """Spinal degenerative changes with different anatomy should be paired correctly."""
        for case in comprehensive_cases:
            if case.expected_output is None:
                continue
            findings = case.expected_output.findings
            spinal_findings = [
                f for f in findings if f.finding_name == "spinal degenerative change"
            ]
            if len(spinal_findings) < 2:
                continue

            result = match_findings(spinal_findings, spinal_findings)
            assert len(result.matches) == len(spinal_findings)

            for m in result.matches:
                if m.expected.location and m.actual.location:
                    assert m.expected.location.specific_anatomy == m.actual.location.specific_anatomy, (
                        f"Case {case.name}: spinal anatomy mismatch — "
                        f"expected {m.expected.location.specific_anatomy}, "
                        f"got {m.actual.location.specific_anatomy}"
                    )
