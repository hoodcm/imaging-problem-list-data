"""Merge, dedupe, and diagnostics helpers for the orchestrator."""

from __future__ import annotations

import json
from collections import defaultdict

from finding_extractor.models import (
    ExtractedReportFindings,
    ExtractionUsage,
    Finding,
    NonFindingText,
)

from .types import ChunkExtractionOutcome, ReportChunk


def _tag_finding_source(finding: Finding, section_name: str) -> Finding:
    if finding.source_section is not None:
        return finding
    if section_name not in {"findings", "impression"}:
        return finding
    return finding.model_copy(update={"source_section": section_name})


def _merge_source_section(existing: str | None, incoming: str | None) -> str | None:
    # When same finding appears in both sections, tag as "both" for downstream awareness.
    if existing == "both" or incoming == "both":
        return "both"
    if existing is None:
        return incoming
    if incoming is None:
        return existing
    if existing == incoming:
        return existing
    if {existing, incoming} == {"findings", "impression"}:
        return "both"
    return existing


def _finding_dedupe_key(finding: Finding) -> str:
    # Nullify source_section so identical findings from different sections merge.
    payload = finding.model_dump(mode="json")
    payload["source_section"] = None
    payload["coding"] = None
    return json.dumps(payload, sort_keys=True)


def _merge_usage(usages: list[ExtractionUsage | None]) -> ExtractionUsage | None:
    present = [u for u in usages if u is not None]
    if not present:
        return None

    details: dict[str, int] = defaultdict(int)
    duration_total = 0
    saw_duration = False
    for usage in present:
        if usage.duration_ms is not None:
            duration_total += usage.duration_ms
            saw_duration = True
        for key, value in usage.details.items():
            details[key] += value

    return ExtractionUsage(
        requests=sum(u.requests for u in present),
        input_tokens=sum(u.input_tokens for u in present),
        output_tokens=sum(u.output_tokens for u in present),
        cache_read_tokens=sum(u.cache_read_tokens for u in present),
        cache_write_tokens=sum(u.cache_write_tokens for u in present),
        duration_ms=duration_total if saw_duration else None,
        details=dict(details),
    )


def _normalize_span_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def merge_extractions(
    outcomes: list[ChunkExtractionOutcome],
) -> tuple[ExtractedReportFindings, ExtractionUsage | None]:
    successful = [o for o in outcomes if o.extraction is not None]
    if not successful:
        raise RuntimeError("No successful section extractions to merge.")

    first_extraction = successful[0].extraction
    assert first_extraction is not None
    exam_info = first_extraction.exam_info
    findings: list[Finding] = []
    finding_index: dict[str, int] = {}
    non_findings: list[NonFindingText] = []
    non_finding_seen: set[tuple[str, str]] = set()

    for outcome in successful:
        extraction = outcome.extraction
        assert extraction is not None

        for finding in extraction.findings:
            tagged = _tag_finding_source(finding, outcome.chunk.section_name)
            key = _finding_dedupe_key(tagged)
            if key in finding_index:
                existing_idx = finding_index[key]
                existing_finding = findings[existing_idx]
                merged_source = _merge_source_section(
                    existing_finding.source_section,
                    tagged.source_section,
                )
                if merged_source != existing_finding.source_section:
                    findings[existing_idx] = existing_finding.model_copy(
                        update={"source_section": merged_source}
                    )
                continue

            finding_index[key] = len(findings)
            findings.append(tagged)

        for non_finding in extraction.non_finding_text:
            key = (non_finding.category, non_finding.text)
            if key in non_finding_seen:
                continue
            non_finding_seen.add(key)
            non_findings.append(non_finding)

    finding_texts = {
        _normalize_span_text(finding.report_text)
        for finding in findings
        if finding.report_text and finding.report_text.strip()
    }
    filtered_non_findings = [
        non_finding
        for non_finding in non_findings
        if _normalize_span_text(non_finding.text) not in finding_texts
    ]

    merged_usage = _merge_usage([o.usage for o in successful])
    return (
        ExtractedReportFindings(
            exam_info=exam_info,
            findings=findings,
            non_finding_text=filtered_non_findings,
        ),
        merged_usage,
    )


def outcomes_to_chunk_map(
    outcomes: list[ChunkExtractionOutcome],
) -> dict[str, ChunkExtractionOutcome]:
    return {
        outcome.chunk.report_chunk_id: outcome
        for outcome in outcomes
        if outcome.extraction is not None
    }


def collect_failed_metadata(
    pending_failed_chunks: list[ReportChunk],
    chunk_last_error_type: dict[str, str],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not pending_failed_chunks:
        return (), ()
    ordered_pending = sorted(pending_failed_chunks, key=lambda c: c.index)
    failed_chunk_ids = tuple(c.report_chunk_id for c in ordered_pending)
    failed_error_types = tuple(
        sorted(
            {chunk_last_error_type.get(c.report_chunk_id, "UnknownError") for c in ordered_pending}
        )
    )
    return failed_chunk_ids, failed_error_types
