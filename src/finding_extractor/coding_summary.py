"""Shared helpers for summarizing inline finding coding."""

from finding_extractor.models import ReportExtraction


def inline_coding_counts(
    extraction: ReportExtraction,
    *,
    unknown_if_absent: bool = True,
) -> tuple[int | None, int | None]:
    """Return (coded, unresolved) counts from findings[].coding.

    If no inline coding is present on any finding, returns `(None, None)` by default.
    Callers that require deterministic numeric counts can set `unknown_if_absent=False`
    to receive `(0, 0)` instead.
    """
    coded = 0
    unresolved = 0
    saw_inline_coding = False
    for finding in extraction.findings:
        if finding.coding is None:
            continue
        saw_inline_coding = True
        if finding.coding.finding_code.status == "coded":
            coded += 1
        elif finding.coding.finding_code.status == "unmapped":
            unresolved += 1
    if saw_inline_coding:
        return coded, unresolved
    if unknown_if_absent:
        return None, None
    return 0, 0

