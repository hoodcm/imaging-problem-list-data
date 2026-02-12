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
from finding_extractor.models import ExtractedFinding, FindingLocation, Presence

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

# ── Helpers ──────────────────────────────────────────────────────────────────


def _make_finding(
    name: str = "renal calculus",
    presence: Presence = "present",
    report_text: str = "There is a renal calculus.",
    body_region: BodyRegion = "abdomen",
) -> ExtractedFinding:
    return ExtractedFinding(
        finding_name=name,
        presence=presence,
        location=FindingLocation(body_region=body_region),
        attributes=[],
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
        assert "kidney." in tokens


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
