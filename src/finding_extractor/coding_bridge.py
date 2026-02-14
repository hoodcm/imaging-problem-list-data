"""Deterministic OIFM and anatomic location coding for extracted findings.

This module provides a non-blocking, additive post-extraction step that maps
free-text finding names to standardized OIFM codes and anatomic location
references using the ``findingmodel`` and ``anatomic-locations`` packages.

Infrastructure failures (e.g. index unavailable) propagate to the caller.
Individual per-finding failures are isolated — one bad finding won't block
the rest.  The caller in ``tasks.py`` catches any propagated exception and
sets ``coding_result=None`` so that extraction is never blocked.
"""

from __future__ import annotations

import structlog
from anatomic_locations import AnatomicLocationIndex
from findingmodel import Index

from finding_extractor.models import (
    AlternateCode,
    CodingBridgeResult,
    ExtractedFinding,
    FindingCoding,
    LocationCoding,
    ReportExtraction,
    UnresolvedFinding,
)

logger = structlog.get_logger(__name__)


async def _code_finding(index: Index, finding: ExtractedFinding) -> FindingCoding:
    """Map a single finding to an OIFM code using a 3-tier strategy.

    1. Exact/synonym — index.get() for ID, name, or synonym lookup.
       search() also does exact match internally, but calling get() first
       lets us distinguish exact vs synonym method in the result.
    2. Search — hybrid FTS+semantic search for the finding name.
    3. Unresolved — no match from either tier.
    """
    name = finding.finding_name.strip()

    # Tier 1: exact or synonym lookup
    entry = await index.get(name)
    if entry is not None:
        is_exact = entry.name.lower() == name.lower()
        return FindingCoding(
            oifm_id=entry.oifm_id,
            oifm_name=entry.name,
            method="exact" if is_exact else "synonym",
        )

    # Tier 2: hybrid search
    results = await index.search(name, limit=3)
    if results:
        top = results[0]
        alternates = [AlternateCode(oifm_id=r.oifm_id, name=r.name) for r in results[1:]]
        return FindingCoding(
            oifm_id=top.oifm_id,
            oifm_name=top.name,
            method="search",
            alternates=alternates,
        )

    # Tier 3: unresolved
    return FindingCoding()


async def _code_location(
    loc_index: AnatomicLocationIndex, finding: ExtractedFinding
) -> LocationCoding:
    """Map a finding's location to an anatomic RID reference."""
    if finding.location is None:
        return LocationCoding()

    loc = finding.location

    # Build query: prefer specific_anatomy, fall back to body_region + laterality
    if loc.specific_anatomy:
        query = loc.specific_anatomy
    else:
        parts = [loc.body_region]
        if loc.laterality:
            parts.append(loc.laterality)
        query = " ".join(parts)

    results = await loc_index.search(query, limit=1)
    if results:
        top = results[0]
        return LocationCoding(
            location_id=top.id,
            location_name=top.description,
        )

    return LocationCoding()


async def apply_coding(extraction: ReportExtraction) -> CodingBridgeResult:
    """Map extracted findings to OIFM codes and anatomic locations.

    Opens the findingmodel and anatomic-locations indices, iterates all
    findings, and returns a ``CodingBridgeResult`` with parallel arrays.

    Raises on infrastructure failures (index unavailable, DB download error).
    Individual per-finding failures are isolated and produce empty codings.
    """
    findings = extraction.findings
    if not findings:
        return CodingBridgeResult(
            finding_codings=[],
            location_codings=[],
            unresolved=[],
            coded_count=0,
            unresolved_count=0,
        )

    async with Index() as fm_index, AnatomicLocationIndex() as loc_index:
        finding_codings: list[FindingCoding] = []
        location_codings: list[LocationCoding] = []
        unresolved: list[UnresolvedFinding] = []

        for i, finding in enumerate(findings):
            # Code finding — isolated per-finding error handling
            try:
                fc = await _code_finding(fm_index, finding)
            except Exception:
                logger.warning(
                    "Finding coding failed for single finding",
                    finding_index=i,
                    finding_name=finding.finding_name,
                    exc_info=True,
                )
                fc = FindingCoding()

            finding_codings.append(fc)

            if fc.method == "unresolved":
                unresolved.append(
                    UnresolvedFinding(
                        finding_name=finding.finding_name,
                        finding_index=i,
                    )
                )

            # Code location — isolated per-finding error handling
            try:
                lc = await _code_location(loc_index, finding)
            except Exception:
                logger.warning(
                    "Location coding failed for single finding",
                    finding_index=i,
                    finding_name=finding.finding_name,
                    exc_info=True,
                )
                lc = LocationCoding()

            location_codings.append(lc)

        coded_count = sum(1 for fc in finding_codings if fc.method != "unresolved")
        return CodingBridgeResult(
            finding_codings=finding_codings,
            location_codings=location_codings,
            unresolved=unresolved,
            coded_count=coded_count,
            unresolved_count=len(unresolved),
        )
