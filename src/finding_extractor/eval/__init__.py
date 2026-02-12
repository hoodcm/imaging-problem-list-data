"""Evaluation harness for extraction quality measurement."""

from finding_extractor.eval.datasets import import_baseline_cases, save_dataset
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
from finding_extractor.eval.reporting import (
    find_latest_run,
    load_run_results,
    print_case_detail,
    print_comparison,
    print_run_summary,
)

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
    "find_latest_run",
    "import_baseline_cases",
    "load_run_results",
    "match_findings",
    "print_case_detail",
    "print_comparison",
    "print_run_summary",
    "save_dataset",
]
