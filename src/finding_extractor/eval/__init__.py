"""Evaluation harness for extraction quality measurement."""

from finding_extractor.eval.evaluators import (
    AttributeEvaluator,
    FindingDetectionEvaluator,
    LocationEvaluator,
    NonFindingClassificationEvaluator,
    PresenceClassificationEvaluator,
    VerbatimQuoteEvaluator,
)
from finding_extractor.eval.matching import FindingMatch, MatchResult, match_findings
from finding_extractor.eval.models import EvalInput, EvalMetadata, EvalRunConfig

__all__ = [
    "AttributeEvaluator",
    "EvalInput",
    "EvalMetadata",
    "EvalRunConfig",
    "FindingDetectionEvaluator",
    "FindingMatch",
    "LocationEvaluator",
    "MatchResult",
    "NonFindingClassificationEvaluator",
    "PresenceClassificationEvaluator",
    "VerbatimQuoteEvaluator",
    "match_findings",
]
