"""Custom evaluators for extraction quality scoring.

Six evaluators covering the key scoring dimensions:
- Finding detection (precision/recall/F1)
- Presence classification accuracy
- Location accuracy (body region, laterality)
- Attribute extraction (precision/recall)
- Verbatim quote exactness
- Non-finding text classification accuracy
"""

from __future__ import annotations

from dataclasses import dataclass

from pydantic_evals.evaluators import EvaluationReason, Evaluator, EvaluatorContext

from finding_extractor.eval.matching import jaccard_similarity, match_findings, tokenize
from finding_extractor.eval.models import EvalInput
from finding_extractor.extraction_agent import check_verbatim
from finding_extractor.models import ReportExtraction


@dataclass
class FindingDetectionEvaluator(Evaluator[EvalInput, ReportExtraction]):
    """Evaluate finding detection precision, recall, and F1."""

    threshold: float = 0.3

    def evaluate(
        self, ctx: EvaluatorContext[EvalInput, ReportExtraction]
    ) -> dict[str, float | EvaluationReason]:
        expected = ctx.expected_output
        actual = ctx.output
        if expected is None:
            return {"finding_precision": 0.0, "finding_recall": 0.0, "finding_f1": 0.0}

        result = match_findings(expected.findings, actual.findings, threshold=self.threshold)

        total_actual = len(result.matches) + len(result.unmatched_actual)
        total_expected = len(result.matches) + len(result.unmatched_expected)

        precision = len(result.matches) / total_actual if total_actual > 0 else 1.0
        recall = len(result.matches) / total_expected if total_expected > 0 else 1.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        reason = (
            f"{len(result.matches)} matched, "
            f"{len(result.unmatched_actual)} FP, "
            f"{len(result.unmatched_expected)} FN"
        )

        return {
            "finding_precision": round(precision, 4),
            "finding_recall": round(recall, 4),
            "finding_f1": EvaluationReason(value=round(f1, 4), reason=reason),
        }


@dataclass
class PresenceClassificationEvaluator(Evaluator[EvalInput, ReportExtraction]):
    """Evaluate presence status classification accuracy on matched findings."""

    threshold: float = 0.3

    def evaluate(
        self, ctx: EvaluatorContext[EvalInput, ReportExtraction]
    ) -> dict[str, float | EvaluationReason]:
        expected = ctx.expected_output
        actual = ctx.output
        if expected is None:
            return {"presence_accuracy": 0.0}

        result = match_findings(expected.findings, actual.findings, threshold=self.threshold)

        if not result.matches:
            return {"presence_accuracy": 1.0 if not expected.findings else 0.0}

        correct = sum(1 for m in result.matches if m.expected.presence == m.actual.presence)
        total = len(result.matches)
        accuracy = round(correct / total, 4)
        reason = f"{correct}/{total} correct"
        return {"presence_accuracy": EvaluationReason(value=accuracy, reason=reason)}


@dataclass
class LocationEvaluator(Evaluator[EvalInput, ReportExtraction]):
    """Evaluate location accuracy on matched findings."""

    threshold: float = 0.3

    def evaluate(
        self, ctx: EvaluatorContext[EvalInput, ReportExtraction]
    ) -> dict[str, float | EvaluationReason]:
        expected = ctx.expected_output
        actual = ctx.output
        if expected is None:
            return {"body_region_accuracy": 0.0, "laterality_accuracy": 0.0}

        result = match_findings(expected.findings, actual.findings, threshold=self.threshold)

        region_total = 0
        region_correct = 0
        lat_total = 0
        lat_correct = 0

        for m in result.matches:
            exp_loc = m.expected.location
            act_loc = m.actual.location

            if exp_loc is not None:
                region_total += 1
                if act_loc is not None and exp_loc.body_region == act_loc.body_region:
                    region_correct += 1

                if exp_loc.laterality is not None:
                    lat_total += 1
                    if act_loc is not None and exp_loc.laterality == act_loc.laterality:
                        lat_correct += 1

        body_region_acc = region_correct / region_total if region_total > 0 else 1.0
        laterality_acc = lat_correct / lat_total if lat_total > 0 else 1.0

        region_reason = f"{region_correct}/{region_total} correct" if region_total > 0 else "no regions to evaluate"
        lat_reason = f"{lat_correct}/{lat_total} correct" if lat_total > 0 else "no laterality to evaluate"

        return {
            "body_region_accuracy": EvaluationReason(value=round(body_region_acc, 4), reason=region_reason),
            "laterality_accuracy": EvaluationReason(value=round(laterality_acc, 4), reason=lat_reason),
        }


@dataclass
class AttributeEvaluator(Evaluator[EvalInput, ReportExtraction]):
    """Evaluate attribute extraction precision and recall on matched findings."""

    threshold: float = 0.3

    def evaluate(
        self, ctx: EvaluatorContext[EvalInput, ReportExtraction]
    ) -> dict[str, float | EvaluationReason]:
        expected = ctx.expected_output
        actual = ctx.output
        if expected is None:
            return {"attribute_precision": 0.0, "attribute_recall": 0.0}

        result = match_findings(expected.findings, actual.findings, threshold=self.threshold)

        total_expected_attrs = 0
        total_actual_attrs = 0
        matched_attrs = 0

        for m in result.matches:
            exp_keys = {a.key for a in m.expected.attributes}
            act_keys = {a.key for a in m.actual.attributes}

            total_expected_attrs += len(exp_keys)
            total_actual_attrs += len(act_keys)
            matched_attrs += len(exp_keys & act_keys)

        precision = matched_attrs / total_actual_attrs if total_actual_attrs > 0 else 1.0
        recall = matched_attrs / total_expected_attrs if total_expected_attrs > 0 else 1.0

        prec_reason = f"{matched_attrs}/{total_actual_attrs} matched" if total_actual_attrs > 0 else "no actual attributes"
        rec_reason = f"{matched_attrs}/{total_expected_attrs} matched" if total_expected_attrs > 0 else "no expected attributes"

        return {
            "attribute_precision": EvaluationReason(value=round(precision, 4), reason=prec_reason),
            "attribute_recall": EvaluationReason(value=round(recall, 4), reason=rec_reason),
        }


@dataclass
class VerbatimQuoteEvaluator(Evaluator[EvalInput, ReportExtraction]):
    """Evaluate verbatim quote exactness using check_verbatim from agent.py."""

    def evaluate(
        self, ctx: EvaluatorContext[EvalInput, ReportExtraction]
    ) -> dict[str, bool | float | EvaluationReason]:
        actual = ctx.output
        report_text = ctx.inputs.report_text

        errors = check_verbatim(report_text, actual)
        total = len(actual.findings) + len(actual.non_finding_text)

        if total == 0:
            return {
                "verbatim_pass": EvaluationReason(value=True, reason="no items to check"),
                "verbatim_rate": 1.0,
            }

        passing = total - len(errors)
        rate = passing / total

        reason = f"{len(errors)}/{total} not verbatim" if errors else f"{total}/{total} verbatim"

        return {
            "verbatim_pass": EvaluationReason(value=not errors, reason=reason),
            "verbatim_rate": round(rate, 4),
        }


@dataclass
class NonFindingClassificationEvaluator(Evaluator[EvalInput, ReportExtraction]):
    """Evaluate non-finding text classification accuracy."""

    def evaluate(self, ctx: EvaluatorContext[EvalInput, ReportExtraction]) -> dict[str, float]:
        expected = ctx.expected_output
        actual = ctx.output
        if expected is None:
            return {"nonfinding_category_accuracy": 0.0}

        if not expected.non_finding_text:
            return {"nonfinding_category_accuracy": 1.0}

        # Match non-finding texts by token overlap, then check categories
        matched = 0
        correct = 0
        used_actual: set[int] = set()

        for exp_nft in expected.non_finding_text:
            exp_tokens = tokenize(exp_nft.text)
            best_idx = -1
            best_overlap = 0.0

            for j, act_nft in enumerate(actual.non_finding_text):
                if j in used_actual:
                    continue
                act_tokens = tokenize(act_nft.text)
                overlap = jaccard_similarity(exp_tokens, act_tokens)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_idx = j

            if best_idx >= 0 and best_overlap >= 0.3:
                used_actual.add(best_idx)
                matched += 1
                if exp_nft.category == actual.non_finding_text[best_idx].category:
                    correct += 1

        accuracy = correct / matched if matched > 0 else 0.0
        return {"nonfinding_category_accuracy": round(accuracy, 4)}
