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

import asyncio
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

_INDEX_INIT_LOCK = asyncio.Lock()
_FINDING_INDEX_CTX: Index | None = None
_LOCATION_INDEX_CTX: AnatomicLocationIndex | None = None
_FINDING_INDEX: Index | None = None
_LOCATION_INDEX: AnatomicLocationIndex | None = None

_BODY_REGION_TO_LOCATION_REGION: dict[str, str] = {
    "chest": "Thorax",
    "abdomen": "Abdomen",
    "pelvis": "Pelvis",
    "head": "Head",
    "neck": "Neck",
    "spine": "Spine",
    "upper extremity": "Upper Extremity",
    "lower extremity": "Lower Extremity",
    "breast": "Breast",
}


def _map_location_region(body_region: str | None) -> str | None:
    if body_region is None:
        return None
    return _BODY_REGION_TO_LOCATION_REGION.get(body_region.lower())


async def _get_reusable_indexes() -> tuple[Index, AnatomicLocationIndex]:
    global _FINDING_INDEX_CTX, _LOCATION_INDEX_CTX, _FINDING_INDEX, _LOCATION_INDEX
    if _FINDING_INDEX is not None and _LOCATION_INDEX is not None:
        return _FINDING_INDEX, _LOCATION_INDEX

    async with _INDEX_INIT_LOCK:
        if _FINDING_INDEX is not None and _LOCATION_INDEX is not None:
            return _FINDING_INDEX, _LOCATION_INDEX

        finding_ctx = Index()
        finding_index = await finding_ctx.__aenter__()
        try:
            location_ctx = AnatomicLocationIndex()
            location_index = await location_ctx.__aenter__()
        except Exception:
            await finding_ctx.__aexit__(None, None, None)
            raise

        _FINDING_INDEX_CTX = finding_ctx
        _LOCATION_INDEX_CTX = location_ctx
        _FINDING_INDEX = finding_index
        _LOCATION_INDEX = location_index
        return finding_index, location_index


async def reset_coding_indexes_for_testing() -> None:
    """Reset reusable coding indexes for tests and process shutdown hooks."""
    global _FINDING_INDEX_CTX, _LOCATION_INDEX_CTX, _FINDING_INDEX, _LOCATION_INDEX
    async with _INDEX_INIT_LOCK:
        if _FINDING_INDEX_CTX is not None:
            await _FINDING_INDEX_CTX.__aexit__(None, None, None)
        if _LOCATION_INDEX_CTX is not None:
            await _LOCATION_INDEX_CTX.__aexit__(None, None, None)
        _FINDING_INDEX_CTX = None
        _LOCATION_INDEX_CTX = None
        _FINDING_INDEX = None
        _LOCATION_INDEX = None


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

    region = _map_location_region(loc.body_region)
    search_kwargs = {"limit": 1}
    if region is not None:
        search_kwargs["region"] = region

    results = await loc_index.search(query, **search_kwargs)
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

    fm_index, loc_index = await _get_reusable_indexes()
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
