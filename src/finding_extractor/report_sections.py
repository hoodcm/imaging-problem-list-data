"""Section detection and content extraction for radiology reports.

This module provides deterministic regex-based section detection for radiology
reports, identifying section boundaries (findings, impression, technique, etc.)
using header pattern matching against a whitelist of known section names.

Basic Usage
-----------

Detect sections in a report::

    from finding_extractor.report_sections import parse_report_sections

    report_text = '''Technique: CT without contrast

    Findings:
    No acute findings.
    Lungs are clear.

    Impression:
    Unremarkable study.'''

    parsed = parse_report_sections(report_text)
    print(parsed.section_names())  # ['technique', 'findings', 'impression']

Extract section content::

    # Get specific section
    findings = parsed.get_section_content('findings')
    print(findings)
    # Output:
    # Findings:
    # No acute findings.
    # Lungs are clear.

    # Get all sections as a dictionary
    for section_name, content in parsed.get_all_section_content().items():
        print(f"=== {section_name.upper()} ===")
        print(content)

LLM Integration
---------------

Use section hints to guide extraction agents::

    from finding_extractor.agent import build_prompt
    from finding_extractor.report_sections import parse_report_sections

    parsed = parse_report_sections(report_text)
    hint = parsed.format_section_hint()

    # Hint provides structured guidance:
    # REPORT STRUCTURE (auto-detected):
    # Sections found: FINDINGS | IMPRESSION
    # → Extract findings from FINDINGS. Extract unique diagnoses from
    #   IMPRESSION (set source_section accordingly). Classify remaining
    #   IMPRESSION text as non_finding_text.

    # build_prompt() automatically includes this hint before the report
    prompt = build_prompt(report_text)

Database Persistence
--------------------

Section structure is automatically persisted to the database::

    from finding_extractor.store import Store
    from finding_extractor.report_sections import (
        parse_report_sections,
        sections_to_json,
        sections_from_json,
    )

    # When upserting a report, sections are detected and stored
    async with Store.connect("sqlite+aiosqlite:///extractions.db") as store:
        report = await store.upsert_report(report_text)
        # report.section_structure_json contains serialized sections

    # Retrieve and deserialize later
    if report.section_structure_json:
        sections = sections_from_json(report.section_structure_json)
        parsed = ParsedReport(sections=sections, original_text=report.report_text)
        print(parsed.section_names())

Section Detection Rules
-----------------------

The parser recognizes these canonical section names via header pattern matching:

- **findings** (aliases: comment, body)
- **impression** (aliases: conclusion)
- **technique**
- **indication** (aliases: clinical information)
- **clinical_history** (aliases: history, clinical history)
- **comparison**
- **recommendation** (aliases: clinical correlation)

Header patterns are matched in priority order:

1. Markdown heading + bold: ``### **Findings:**``
2. Bold only: ``**Technique:**``
3. All caps: ``FINDINGS:``
4. Title case with content: ``History: flank pain``

Subsection headers (e.g., ``**Liver:**``, ``**Lungs:**``) are intentionally
excluded using a whitelist approach.

Data Structures
---------------

ParsedReport
    Result of parsing a report, with methods for accessing section metadata
    and content.

ReportSection
    A single detected section with canonical name, line boundaries, and the
    raw header text that triggered detection.

Functions
---------

parse_report_sections(report_text: str) -> ParsedReport
    Main entry point for section detection.

sections_to_json(sections: list[ReportSection]) -> str | None
    Serialize sections to JSON for database storage.

sections_from_json(data: str) -> list[ReportSection]
    Deserialize sections from a database JSON string.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import TypeAdapter

# ---------------------------------------------------------------------------
# Header alias map — only these canonical names are recognized
# ---------------------------------------------------------------------------

_HEADER_ALIASES: dict[str, str] = {
    "findings": "findings",
    "comment": "findings",
    "body": "findings",
    "impression": "impression",
    "conclusion": "impression",
    "technique": "technique",
    "indication": "indication",
    "clinical information": "indication",
    "history": "clinical_history",
    "clinical history": "clinical_history",
    "comparison": "comparison",
    "recommendation": "recommendation",
    "clinical correlation": "recommendation",
}

# ---------------------------------------------------------------------------
# Header detection patterns (compiled, priority order)
# ---------------------------------------------------------------------------

# Priority 1: ### **Findings:**
_RE_MD_HEADING_BOLD = re.compile(r"^#{1,4}\s*\*\*(.+?):\s*\*\*", re.MULTILINE)
# Priority 2: **Technique:**
_RE_BOLD = re.compile(r"^\*\*(.+?):\s*\*\*", re.MULTILINE)
# Priority 3: FINDINGS:
_RE_ALLCAPS = re.compile(r"^([A-Z][A-Z\s]+):\s*$", re.MULTILINE)
# Priority 4: Title case with content after colon (e.g. "History: flank pain").
# This is the loosest pattern — safety relies on the _HEADER_ALIASES whitelist.
# Uses [ \t] in header name to prevent matching across newlines; colon can be
# followed by space/tab or end-of-line.
_RE_TITLE = re.compile(r"^([A-Za-z][A-Za-z \t]+):(?:[ \t]|$)", re.MULTILINE)

_HEADER_PATTERNS = [_RE_MD_HEADING_BOLD, _RE_BOLD, _RE_ALLCAPS, _RE_TITLE]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReportSection:
    """A detected section within a radiology report."""

    name: str  # canonical name (e.g. "findings", "impression")
    start_line: int  # 0-based inclusive
    end_line: int  # 0-based exclusive
    header_text: str  # raw header line that triggered detection


# TypeAdapter for serializing/deserializing lists of sections via Pydantic.
_SECTIONS_ADAPTER: TypeAdapter[list[ReportSection]] = TypeAdapter(list[ReportSection])


@dataclass(frozen=True)
class ParsedReport:
    """Result of parsing a radiology report for section structure.

    Attributes:
        sections: List of detected sections in document order
        original_text: Original report text (stored for content extraction)
    """

    sections: list[ReportSection] = field(default_factory=list)
    original_text: str = ""

    def format_section_hint(self) -> str | None:
        """Compact hint for the user prompt.  Returns None if no sections detected."""
        if not self.sections:
            return None

        names_upper = [s.name.upper() for s in self.sections]
        lines = [
            "REPORT STRUCTURE (auto-detected):",
            f"Sections found: {' | '.join(names_upper)}",
        ]

        has_findings = self.has_section("findings")
        has_impression = self.has_section("impression")
        if has_findings and has_impression:
            lines.append(
                "→ Extract findings from FINDINGS. Extract unique diagnoses from "
                "IMPRESSION (set source_section accordingly). Classify remaining "
                "IMPRESSION text as non_finding_text."
            )

        return "\n".join(lines)

    def get_section(self, name: str) -> ReportSection | None:
        """Return the first section matching *name*, or None."""
        for s in self.sections:
            if s.name == name:
                return s
        return None

    def has_section(self, name: str) -> bool:
        """Check whether a section with *name* exists."""
        return self.get_section(name) is not None

    def section_names(self) -> list[str]:
        """Return canonical names in document order."""
        return [s.name for s in self.sections]

    def get_section_content(self, section_name: str) -> str | None:
        """Get the text content of a specific section.

        Args:
            section_name: Canonical section name (e.g., "findings", "impression")

        Returns:
            Section text content or None if section not found

        Example:
            >>> parsed = parse_report_sections(report_text)
            >>> findings = parsed.get_section_content('findings')
            >>> print(findings)
            Findings:
            No acute findings.
        """
        section = self.get_section(section_name)
        if section is None:
            return None
        lines = self.original_text.split('\n')
        return '\n'.join(lines[section.start_line:section.end_line])

    def get_all_section_content(self) -> dict[str, str]:
        """Get all section content as a dictionary.

        Returns:
            Dict mapping section names to their text content

        Example:
            >>> parsed = parse_report_sections(report_text)
            >>> for name, content in parsed.get_all_section_content().items():
            ...     print(f"=== {name.upper()} ===")
            ...     print(content)
        """
        result: dict[str, str] = {}
        for section in self.sections:
            content = self.get_section_content(section.name)
            if content is not None:
                result[section.name] = content
        return result


def sections_to_json(sections: list[ReportSection]) -> str | None:
    """Serialize sections to a JSON string for DB storage.  Returns None if empty."""
    if not sections:
        return None
    return _SECTIONS_ADAPTER.dump_json(sections).decode()


def sections_from_json(data: str) -> list[ReportSection]:
    """Deserialize sections from a DB JSON string."""
    return _SECTIONS_ADAPTER.validate_json(data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def parse_report_sections(report_text: str) -> ParsedReport:
    """Detect sections in a radiology report.  Best-effort, deterministic."""
    lines = report_text.split("\n")

    # Collect (line_index, canonical_name, header_line) for detected headers
    detected: list[tuple[int, str, str]] = []
    matched_lines: set[int] = set()

    for pattern in _HEADER_PATTERNS:
        for match in pattern.finditer(report_text):
            # Determine which line this match is on
            line_start = report_text.count("\n", 0, match.start())
            if line_start in matched_lines:
                continue  # already matched by a higher-priority pattern

            raw_name = match.group(1).strip().lower()
            canonical = _HEADER_ALIASES.get(raw_name)
            if canonical is None:
                continue  # not in whitelist → skip (subsections, etc.)

            detected.append((line_start, canonical, lines[line_start].strip()))
            matched_lines.add(line_start)

    if not detected:
        return ParsedReport(original_text=report_text)

    # Sort by line position
    detected.sort(key=lambda t: t[0])

    # Build ReportSection objects with boundaries
    sections: list[ReportSection] = []
    total_lines = len(lines)
    for i, (start, name, header_text) in enumerate(detected):
        end = detected[i + 1][0] if i + 1 < len(detected) else total_lines
        sections.append(
            ReportSection(
                name=name,
                start_line=start,
                end_line=end,
                header_text=header_text,
            )
        )

    return ParsedReport(sections=sections, original_text=report_text)
