"""Deterministic + adjudicated OIFM/location coding for extracted findings."""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

import structlog
from anatomic_locations import AnatomicLocationIndex
from findingmodel import Index

from finding_extractor.coding_agents import (
    adjudicate_finding_candidate,
    adjudicate_location_candidate,
)
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


@dataclass(frozen=True)
class _SingleCodingResult:
    finding_index: int
    finding_name: str
    finding_coding: FindingCoding
    location_coding: LocationCoding
    unresolved: UnresolvedFinding | None


@dataclass(frozen=True)
class _LocationCandidate:
    location_id: str
    location_name: str


def _normalized_tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if token}


def _is_confident_search_match(query: str, candidate_name: str) -> bool:
    query_tokens = _normalized_tokens(query)
    candidate_tokens = _normalized_tokens(candidate_name)
    if not query_tokens or not candidate_tokens:
        return False
    overlap = query_tokens & candidate_tokens
    if not overlap:
        return False
    overlap_ratio = len(overlap) / min(len(query_tokens), len(candidate_tokens))
    return overlap_ratio >= 0.34


def _map_location_region(body_region: str | None) -> str | None:
    if body_region is None:
        return None
    return _BODY_REGION_TO_LOCATION_REGION.get(body_region.lower())


async def _index_get(index: Index, name: str):
    return await index.get(name)


async def _index_search(index: Index, name: str, *, limit: int):
    return await index.search(name, limit=limit)


async def _location_search(
    loc_index: AnatomicLocationIndex,
    query: str,
    *,
    limit: int,
    region: str | None,
):
    if region is not None:
        return await loc_index.search(query, limit=limit, region=region)
    return await loc_index.search(query, limit=limit)


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


async def close_reusable_coding_indexes() -> None:
    """Close and clear reusable coding indexes (worker lifecycle + tests)."""
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


async def reset_coding_indexes_for_testing() -> None:
    """Backward-compatible alias for tests using the old helper name."""
    await close_reusable_coding_indexes()


async def _code_finding(index: Index, finding: ExtractedFinding) -> FindingCoding:
    """Map a single finding to an OIFM code with deterministic fast-path."""
    name = finding.finding_name.strip()

    entry = await _index_get(index, name)
    if entry is not None:
        is_exact = entry.name.lower() == name.lower()
        return FindingCoding(
            oifm_id=entry.oifm_id,
            oifm_name=entry.name,
            method="exact" if is_exact else "synonym",
        )

    results = await _index_search(index, name, limit=3)
    if results:
        top = results[0]
        alternates = [AlternateCode(oifm_id=r.oifm_id, name=r.name) for r in results[1:]]
        if not _is_confident_search_match(name, top.name):
            return FindingCoding(
                method="unresolved",
                alternates=[AlternateCode(oifm_id=r.oifm_id, name=r.name) for r in results],
            )
        return FindingCoding(
            oifm_id=top.oifm_id,
            oifm_name=top.name,
            method="search",
            alternates=alternates,
        )

    return FindingCoding()


def _build_location_query(finding: ExtractedFinding) -> tuple[str, str | None] | None:
    if finding.location is None:
        return None

    loc = finding.location
    if loc.specific_anatomy:
        query = loc.specific_anatomy
    else:
        parts = [loc.body_region]
        if loc.laterality:
            parts.append(loc.laterality)
        query = " ".join(parts)

    region = _map_location_region(loc.body_region)
    return query, region


async def _code_location_with_candidates(
    loc_index: AnatomicLocationIndex,
    finding: ExtractedFinding,
) -> tuple[LocationCoding, str | None, list[_LocationCandidate]]:
    """Map a finding location with deterministic fast-path + ambiguity candidates."""
    built = _build_location_query(finding)
    if built is None:
        return LocationCoding(), None, []

    query, region = built
    results = await _location_search(loc_index, query, limit=3, region=region)
    if not results:
        return LocationCoding(), query, []

    top = results[0]
    if _is_confident_search_match(query, top.description):
        return (
            LocationCoding(location_id=top.id, location_name=top.description),
            query,
            [],
        )

    candidates = [
        _LocationCandidate(location_id=result.id, location_name=result.description)
        for result in results
    ]
    return LocationCoding(), query, candidates


async def _code_single_finding(
    *,
    finding_index: int,
    finding: ExtractedFinding,
    fm_index: Index,
    loc_index: AnatomicLocationIndex,
    adjudicate_ambiguous: bool,
    adjudicator_model: str | None,
    adjudicator_reasoning: str | None,
) -> _SingleCodingResult:
    unresolved: UnresolvedFinding | None = None

    finding_failed = False
    try:
        finding_coding = await _code_finding(fm_index, finding)
    except Exception:
        logger.warning(
            "Finding coding failed for single finding",
            finding_index=finding_index,
            finding_name=finding.finding_name,
            exc_info=True,
        )
        finding_failed = True
        finding_coding = FindingCoding()
        unresolved = UnresolvedFinding(
            finding_name=finding.finding_name,
            finding_index=finding_index,
            reason="coding_error",
        )

    if (
        not finding_failed
        and finding_coding.method == "unresolved"
        and finding_coding.alternates
        and adjudicate_ambiguous
        and adjudicator_model is not None
    ):
        try:
            adjudication = await adjudicate_finding_candidate(
                finding_name=finding.finding_name,
                candidates=finding_coding.alternates,
                model_name=adjudicator_model,
                reasoning=adjudicator_reasoning,
            )
            if not adjudication.unresolved and adjudication.selected_id is not None:
                chosen = next(
                    (candidate for candidate in finding_coding.alternates if candidate.oifm_id == adjudication.selected_id),
                    None,
                )
                if chosen is not None:
                    finding_coding = FindingCoding(
                        oifm_id=chosen.oifm_id,
                        oifm_name=chosen.name,
                        method="agent",
                        alternates=[
                            candidate
                            for candidate in finding_coding.alternates
                            if candidate.oifm_id != chosen.oifm_id
                        ],
                    )
        except Exception:
            logger.warning(
                "Finding adjudication failed; keeping unresolved deterministic result",
                finding_index=finding_index,
                finding_name=finding.finding_name,
                exc_info=True,
            )

    if unresolved is None and finding_coding.method == "unresolved":
        reason = "search_low_confidence" if finding_coding.alternates else "no_match"
        unresolved = UnresolvedFinding(
            finding_name=finding.finding_name,
            finding_index=finding_index,
            reason=reason,
            candidates=finding_coding.alternates,
        )

    try:
        location_coding, query, location_candidates = await _code_location_with_candidates(
            loc_index,
            finding,
        )
    except Exception:
        logger.warning(
            "Location coding failed for single finding",
            finding_index=finding_index,
            finding_name=finding.finding_name,
            exc_info=True,
        )
        location_coding, query, location_candidates = LocationCoding(), None, []

    if (
        location_candidates
        and location_coding.location_id is None
        and adjudicate_ambiguous
        and adjudicator_model is not None
        and query is not None
    ):
        try:
            adjudication = await adjudicate_location_candidate(
                query=query,
                candidates=[
                    AlternateCode(oifm_id=candidate.location_id, name=candidate.location_name)
                    for candidate in location_candidates
                ],
                model_name=adjudicator_model,
                reasoning=adjudicator_reasoning,
            )
            if not adjudication.unresolved and adjudication.selected_id is not None:
                chosen = next(
                    (
                        candidate
                        for candidate in location_candidates
                        if candidate.location_id == adjudication.selected_id
                    ),
                    None,
                )
                if chosen is not None:
                    location_coding = LocationCoding(
                        location_id=chosen.location_id,
                        location_name=chosen.location_name,
                    )
        except Exception:
            logger.warning(
                "Location adjudication failed; keeping deterministic result",
                finding_index=finding_index,
                finding_name=finding.finding_name,
                exc_info=True,
            )

    return _SingleCodingResult(
        finding_index=finding_index,
        finding_name=finding.finding_name,
        finding_coding=finding_coding,
        location_coding=location_coding,
        unresolved=unresolved,
    )


async def apply_coding(
    extraction: ReportExtraction,
    *,
    adjudicate_ambiguous: bool = True,
    adjudicator_model: str | None = None,
    adjudicator_reasoning: str | None = None,
    max_concurrency: int = 5,
) -> CodingBridgeResult:
    """Map extracted findings to OIFM/location codes.

    Deterministic index lookup/search runs first. Optional adjudicator agents are
    invoked only for ambiguous candidate sets.

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
    semaphore = asyncio.Semaphore(max(1, max_concurrency))
    results: list[_SingleCodingResult | None] = [None] * len(findings)

    async def _run_indexed(i: int, finding: ExtractedFinding) -> None:
        async with semaphore:
            results[i] = await _code_single_finding(
                finding_index=i,
                finding=finding,
                fm_index=fm_index,
                loc_index=loc_index,
                adjudicate_ambiguous=adjudicate_ambiguous,
                adjudicator_model=adjudicator_model,
                adjudicator_reasoning=adjudicator_reasoning,
            )

    await asyncio.gather(*(_run_indexed(i, finding) for i, finding in enumerate(findings)))

    materialized = [result for result in results if result is not None]
    materialized.sort(key=lambda item: item.finding_index)

    finding_codings = [item.finding_coding for item in materialized]
    location_codings = [item.location_coding for item in materialized]
    unresolved = [item.unresolved for item in materialized if item.unresolved is not None]

    coded_count = sum(1 for fc in finding_codings if fc.method != "unresolved")
    return CodingBridgeResult(
        finding_codings=finding_codings,
        location_codings=location_codings,
        unresolved=unresolved,
        coded_count=coded_count,
        unresolved_count=len(unresolved),
    )
