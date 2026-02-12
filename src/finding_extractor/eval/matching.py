"""Finding matching algorithm for evaluation scoring.

Uses greedy best-match with Jaccard token similarity on finding_name + report_text,
plus bonuses for matching presence, location, and attributes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from finding_extractor.models import ExtractedFinding

DEFAULT_MATCH_THRESHOLD = 0.3
_PRESENCE_BONUS = 0.1
_BODY_REGION_BONUS = 0.05
_LATERALITY_BONUS = 0.05
_ANATOMY_BONUS = 0.05
_ATTRIBUTE_BONUS = 0.03

_WORD_RE = re.compile(r"\w+", re.UNICODE)


def tokenize(text: str) -> set[str]:
    """Tokenize text into lowercase words, stripping punctuation."""
    return set(_WORD_RE.findall(text.lower()))


def _finding_tokens(finding: ExtractedFinding) -> set[str]:
    """Extract tokens from a finding for similarity comparison."""
    tokens = tokenize(finding.finding_name)
    tokens |= tokenize(finding.report_text)
    return tokens


def _anatomy_tokens(finding: ExtractedFinding) -> set[str]:
    """Precompute specific_anatomy tokens for a finding (empty set if absent)."""
    if finding.location and finding.location.specific_anatomy:
        return tokenize(finding.location.specific_anatomy)
    return set()


def _location_bonus(
    expected: ExtractedFinding,
    actual: ExtractedFinding,
    exp_anatomy: set[str],
    act_anatomy: set[str],
) -> float:
    """Compute location-based tiebreaker bonus for matching.

    Returns up to 0.15: +0.05 body_region, +0.05 laterality, +0.05 anatomy overlap.
    Anatomy tokens are precomputed and passed in to avoid redundant tokenization.
    """
    exp_loc = expected.location
    act_loc = actual.location
    if exp_loc is None or act_loc is None:
        return 0.0

    bonus = 0.0

    if exp_loc.body_region == act_loc.body_region:
        bonus += _BODY_REGION_BONUS

    if (
        exp_loc.laterality is not None
        and act_loc.laterality is not None
        and exp_loc.laterality == act_loc.laterality
    ):
        bonus += _LATERALITY_BONUS

    if exp_anatomy and act_anatomy:
        overlap = len(exp_anatomy & act_anatomy)
        total = len(exp_anatomy | act_anatomy)
        bonus += _ANATOMY_BONUS * (overlap / total)

    return bonus


def _attribute_bonus(expected: ExtractedFinding, actual: ExtractedFinding) -> float:
    """Compute attribute-based tiebreaker bonus for matching.

    Returns up to 0.03 scaled by attribute key-value overlap ratio.
    """
    if not expected.attributes or not actual.attributes:
        return 0.0

    exp_pairs = {(a.key, a.value.lower().strip()) for a in expected.attributes}
    act_pairs = {(a.key, a.value.lower().strip()) for a in actual.attributes}

    overlap = len(exp_pairs & act_pairs)
    total = len(exp_pairs | act_pairs)
    return _ATTRIBUTE_BONUS * (overlap / total)


def jaccard_similarity(tokens_a: set[str], tokens_b: set[str]) -> float:
    """Compute Jaccard similarity between two token sets."""
    if not tokens_a or not tokens_b:
        return 0.0
    intersection = tokens_a & tokens_b
    union = tokens_a | tokens_b
    return len(intersection) / len(union)


@dataclass(frozen=True)
class FindingMatch:
    """A matched pair of expected and actual findings."""

    expected: ExtractedFinding
    actual: ExtractedFinding
    similarity: float


@dataclass(frozen=True)
class MatchResult:
    """Result of matching expected findings to actual findings."""

    matches: list[FindingMatch]
    unmatched_expected: list[ExtractedFinding]  # False negatives
    unmatched_actual: list[ExtractedFinding]  # False positives


def match_findings(
    expected: list[ExtractedFinding],
    actual: list[ExtractedFinding],
    threshold: float = DEFAULT_MATCH_THRESHOLD,
) -> MatchResult:
    """Match expected findings to actual findings using greedy best-match.

    Uses Jaccard token similarity on finding_name + report_text with
    bonuses for matching presence, location, and attributes.

    Args:
        expected: Ground truth findings.
        actual: Findings produced by the extractor.
        threshold: Minimum similarity to consider a match.

    Returns:
        MatchResult with matched pairs, unmatched expected (FN), and unmatched actual (FP).
    """
    if not expected and not actual:
        return MatchResult(matches=[], unmatched_expected=[], unmatched_actual=[])
    if not expected:
        return MatchResult(matches=[], unmatched_expected=[], unmatched_actual=list(actual))
    if not actual:
        return MatchResult(matches=[], unmatched_expected=list(expected), unmatched_actual=[])

    # Precompute tokens
    expected_tokens = [_finding_tokens(f) for f in expected]
    actual_tokens = [_finding_tokens(f) for f in actual]
    expected_anatomy = [_anatomy_tokens(f) for f in expected]
    actual_anatomy = [_anatomy_tokens(f) for f in actual]

    # Compute pairwise similarities
    candidates: list[tuple[float, int, int]] = []
    for i, exp_tok in enumerate(expected_tokens):
        for j, act_tok in enumerate(actual_tokens):
            sim = jaccard_similarity(exp_tok, act_tok)
            # Presence bonus: +0.1 if presence matches
            if expected[i].presence == actual[j].presence:
                sim += _PRESENCE_BONUS
            # Location bonus: up to +0.15 for matching location fields
            sim += _location_bonus(
                expected[i], actual[j], expected_anatomy[i], actual_anatomy[j]
            )
            # Attribute bonus: up to +0.03 for matching attribute pairs
            sim += _attribute_bonus(expected[i], actual[j])
            if sim >= threshold:
                candidates.append((sim, i, j))

    # Sort by similarity descending (greedy best-match)
    candidates.sort(key=lambda x: x[0], reverse=True)

    matched_expected: set[int] = set()
    matched_actual: set[int] = set()
    matches: list[FindingMatch] = []

    for sim, exp_idx, act_idx in candidates:
        if exp_idx in matched_expected or act_idx in matched_actual:
            continue
        matches.append(
            FindingMatch(
                expected=expected[exp_idx],
                actual=actual[act_idx],
                similarity=sim,
            )
        )
        matched_expected.add(exp_idx)
        matched_actual.add(act_idx)

    unmatched_exp = [expected[i] for i in range(len(expected)) if i not in matched_expected]
    unmatched_act = [actual[i] for i in range(len(actual)) if i not in matched_actual]

    return MatchResult(
        matches=matches,
        unmatched_expected=unmatched_exp,
        unmatched_actual=unmatched_act,
    )
