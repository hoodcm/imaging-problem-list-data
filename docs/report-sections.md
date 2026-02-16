# Report Section Detection

This guide covers how to use the `report_sections` module for detecting and extracting structured sections from radiology reports.

## Quick Start

### Basic Section Detection

Detect sections in a report and list their names:

```python
from finding_extractor.report_sections import parse_report_sections

report_text = '''Technique: CT without contrast

Findings:
No acute findings.
Lungs are clear.

Impression:
Unremarkable study.'''

parsed = parse_report_sections(report_text)
print(parsed.section_names())  # ['technique', 'findings', 'impression']
```

### Extract Section Content

Get the text content of a specific section:

```python
# Get a single section
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
    print()
```

### Check for Specific Sections

```python
if parsed.has_section('impression'):
    impression = parsed.get_section_content('impression')
    print("Impression:", impression)

if parsed.has_section('findings'):
    findings = parsed.get_section_content('findings')
    print("Findings:", findings)
```

## How Section Detection Works

### Recognized Section Names

The parser recognizes these canonical section names:

| Canonical Name | Aliases |
|---------------|---------|
| `findings` | comment, body |
| `impression` | conclusion |
| `technique` | |
| `indication` | clinical information |
| `clinical_history` | history, clinical history |
| `comparison` | |
| `recommendation` | clinical correlation |

### Header Pattern Matching

Headers are matched in **priority order**:

1. **Markdown heading + bold**: `### **Findings:**`
2. **Bold only**: `**Technique:**`
3. **All caps**: `FINDINGS:`
4. **Title case with content**: `History: flank pain`

The parser uses a **whitelist approach** to avoid matching subsection headers like `**Liver:**` or `**Lungs:**`. Only headers that map to canonical section names (via the alias table) are recognized.

### Section Boundaries

Sections are bounded by:
- **Start**: The line containing the section header
- **End**: The line before the next section header (or end of report)

Example:

```
Line 0: Technique: CT without contrast    <- technique section starts
Line 1:
Line 2: Findings:                         <- findings section starts (technique ends)
Line 3: No acute findings.
Line 4:
Line 5: Impression:                       <- impression section starts (findings ends)
Line 6: Unremarkable study.               <- impression extends to end
```

## Usage in Extraction

### LLM Guidance with Section Hints

The extraction agent automatically uses section hints to guide the LLM:

```python
from finding_extractor.extraction_agent import build_prompt

# build_prompt() automatically calls parse_report_sections()
prompt = build_prompt(report_text)

# When both findings and impression sections exist, the prompt includes:
# REPORT STRUCTURE (auto-detected):
# Sections found: FINDINGS | IMPRESSION
# → Extract findings from FINDINGS. Extract unique diagnoses from
#   IMPRESSION (set source_section accordingly). Classify remaining
#   IMPRESSION text as non_finding_text.
```

The hint is placed **before** the report delimiters, so verbatim validation against the original text is unaffected.

### Source Section Tracking

Extracted findings include a `source_section` field that indicates where in the report the finding was extracted from:

```python
from finding_extractor.models import ExtractedFinding

finding = ExtractedFinding(
    finding_name="kidney stone",
    presence="present",
    report_text="3 mm stone in the right kidney",
    source_section="findings"  # or "impression" or "both"
)
```

Valid values:
- `"findings"` — extracted from the findings section
- `"impression"` — unique diagnosis from the impression section
- `"both"` — mentioned in both sections (rare)

## Database Persistence

### Automatic Storage

Section structure is automatically stored when upserting reports:

```python
from finding_extractor.store import Store

async with Store.connect("sqlite+aiosqlite:///extractions.db") as store:
    # Section detection happens automatically during upsert
    report = await store.upsert_report(report_text)

    # Section structure is stored as JSON
    print(report.section_structure_json)
    # [{"name":"findings","start_line":2,"end_line":5,"header_text":"Findings:"}]
```

### Lazy Backfill

Pre-existing reports without section structure are **automatically backfilled** on first access:

```python
# On second upsert of the same report (by hash), sections are computed if missing
report = await store.upsert_report(report_text)
```

### Manual Serialization/Deserialization

```python
from finding_extractor.report_sections import (
    parse_report_sections,
    sections_to_json,
    sections_from_json,
)

# Parse and serialize
parsed = parse_report_sections(report_text)
json_str = sections_to_json(parsed.sections)

# Deserialize later
sections = sections_from_json(json_str)
parsed_restored = ParsedReport(sections=sections, original_text=report_text)
```

## API Reference

### Functions

#### `parse_report_sections(report_text: str) -> ParsedReport`

Detect sections in a radiology report. Best-effort, deterministic.

**Parameters:**
- `report_text` — Full text of the radiology report

**Returns:**
- `ParsedReport` object containing detected sections and the original text

#### `sections_to_json(sections: list[ReportSection]) -> str | None`

Serialize sections to a JSON string for database storage.

**Returns:**
- JSON string or `None` if sections list is empty

#### `sections_from_json(data: str) -> list[ReportSection]`

Deserialize sections from a database JSON string.

**Parameters:**
- `data` — JSON string from database

**Returns:**
- List of `ReportSection` objects

### Classes

#### `ParsedReport`

Result of parsing a report for section structure.

**Attributes:**
- `sections: list[ReportSection]` — Detected sections in document order
- `original_text: str` — Original report text (for content extraction)

**Methods:**

##### `format_section_hint() -> str | None`

Generate a compact hint for the LLM prompt. Returns `None` if no sections detected.

##### `get_section(name: str) -> ReportSection | None`

Get the first section matching the given canonical name.

##### `has_section(name: str) -> bool`

Check whether a section with the given name exists.

##### `section_names() -> list[str]`

Get all canonical section names in document order.

##### `get_section_content(section_name: str) -> str | None`

Get the text content of a specific section.

**Example:**
```python
findings = parsed.get_section_content('findings')
```

##### `get_all_section_content() -> dict[str, str]`

Get all section content as a dictionary mapping section names to their text.

**Example:**
```python
for name, content in parsed.get_all_section_content().items():
    print(f"{name}: {content}")
```

#### `ReportSection`

A detected section within a radiology report.

**Attributes:**
- `name: str` — Canonical section name (e.g., "findings", "impression")
- `start_line: int` — 0-based inclusive start line
- `end_line: int` — 0-based exclusive end line
- `header_text: str` — Raw header line that triggered detection

## Common Patterns

### Process Only Reports with Structure

```python
parsed = parse_report_sections(report_text)
if not parsed.sections:
    print("Unstructured report - no sections detected")
else:
    print(f"Structured report with {len(parsed.sections)} sections")
```

### Extract Findings and Impression Separately

```python
parsed = parse_report_sections(report_text)

if parsed.has_section('findings'):
    findings = parsed.get_section_content('findings')
    # Process findings section

if parsed.has_section('impression'):
    impression = parsed.get_section_content('impression')
    # Process impression section
```

### Generate Section Summary

```python
def summarize_report_structure(report_text: str) -> str:
    parsed = parse_report_sections(report_text)
    if not parsed.sections:
        return "Unstructured report"

    lines = [f"Detected {len(parsed.sections)} sections:"]
    for section in parsed.sections:
        line_count = section.end_line - section.start_line
        lines.append(f"  - {section.name}: {line_count} lines")
    return "\n".join(lines)
```

## Edge Cases and Limitations

### Unstructured Reports

Reports without recognized section headers return an empty `ParsedReport`:

```python
parsed = parse_report_sections("The heart is normal. No pleural effusion.")
print(parsed.sections)  # []
print(parsed.format_section_hint())  # None
```

### Subsections Are Ignored

Subsection headers like `**Liver:**` or `**Lungs:**` are intentionally excluded:

```python
report = '''Findings:
**Liver:** Normal.
**Spleen:** Normal.'''

parsed = parse_report_sections(report)
print(parsed.section_names())  # ['findings'] only
```

### Unknown Headers Are Ignored

Headers not in the canonical name whitelist are skipped:

```python
report = '''Protocol: Standard.

Findings: Normal.'''

parsed = parse_report_sections(report)
print(parsed.section_names())  # ['findings'] - 'protocol' is not recognized
```

### Multiple Instances of Same Section

If the same canonical name appears multiple times (e.g., via different aliases), only the first match is returned by `get_section()`:

```python
report = '''Findings: Normal.

Comment: Additional note.'''  # "comment" is an alias for "findings"

parsed = parse_report_sections(report)
section = parsed.get_section('findings')
print(section.header_text)  # "Findings:" (first match)
```

## Migration Notes

If you're migrating from the old `preprocess` module:

| Old API | New API |
|---------|---------|
| `preprocess_report()` | `parse_report_sections()` |
| `PreprocessedReport` | `ParsedReport` |
| `from finding_extractor.preprocess import` | `from finding_extractor.report_sections import` |

All other functions and classes remain unchanged (`sections_to_json`, `sections_from_json`, `ReportSection`).
