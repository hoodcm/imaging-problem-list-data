"""Shared verbatim text matching helpers."""


def normalize_whitespace(text: str) -> str:
    """Collapse runs of whitespace to single spaces and strip."""
    return " ".join(text.split())


def verbatim_match(span: str, report_text: str) -> bool:
    """Check if *span* appears in *report_text*, tolerating whitespace differences."""
    snippet = span.strip()
    if not snippet:
        return False
    if snippet in report_text:
        return True
    return normalize_whitespace(snippet) in normalize_whitespace(report_text)
