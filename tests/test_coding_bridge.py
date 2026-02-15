"""Tests for the OIFM and anatomic location coding bridge."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from finding_extractor.coding_bridge import (
    _code_finding,
    _code_location,
    apply_coding,
    reset_coding_indexes_for_testing,
)
from finding_extractor.models import (
    ExamInfo,
    ExtractedFinding,
    FindingLocation,
    Presence,
    ReportExtraction,
)

# ---------------------------------------------------------------------------
# Lightweight fakes for findingmodel.Index and anatomic_locations results
# ---------------------------------------------------------------------------


@dataclass
class FakeIndexEntry:
    """Mimics findingmodel.IndexEntry for testing."""

    oifm_id: str
    name: str
    synonyms: list[str] | None = None


@dataclass
class FakeAnatomicLocation:
    """Mimics anatomic_locations.AnatomicLocation for testing."""

    id: str
    description: str


def _make_finding(
    name: str,
    presence: Presence = "present",
    body_region: str | None = None,
    specific_anatomy: str | None = None,
    laterality: str | None = None,
) -> ExtractedFinding:
    location = None
    if body_region:
        location = FindingLocation(
            body_region=body_region,  # type: ignore[arg-type]  # test helper accepts any str
            specific_anatomy=specific_anatomy,
            laterality=laterality,  # type: ignore[arg-type]  # test helper accepts any str
        )
    return ExtractedFinding(
        finding_name=name,
        presence=presence,
        location=location,
        report_text=f"Test text for {name}.",
    )


def _make_extraction(findings: list[ExtractedFinding]) -> ReportExtraction:
    return ReportExtraction(
        exam_info=ExamInfo(study_description="Test Study"),
        findings=findings,
    )


def _mock_indices(monkeypatch, *, fm_index, loc_index):
    """Wire mock Index and AnatomicLocationIndex into coding_bridge."""
    fm_index.__aenter__ = AsyncMock(return_value=fm_index)
    fm_index.__aexit__ = AsyncMock(return_value=False)
    loc_index.__aenter__ = AsyncMock(return_value=loc_index)
    loc_index.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("finding_extractor.coding_bridge.Index", lambda: fm_index)
    monkeypatch.setattr("finding_extractor.coding_bridge.AnatomicLocationIndex", lambda: loc_index)


@pytest_asyncio.fixture(autouse=True)
async def _reset_reusable_indexes():
    await reset_coding_indexes_for_testing()
    yield
    await reset_coding_indexes_for_testing()


# ---------------------------------------------------------------------------
# _code_finding tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_exact_match():
    """Finding name matching an OIFM entry exactly."""
    index = AsyncMock()
    index.get = AsyncMock(
        return_value=FakeIndexEntry(
            oifm_id="OIFM_GMTS_016552",
            name="urinary tract calculus",
            synonyms=["kidney stone"],
        )
    )

    finding = _make_finding("urinary tract calculus")
    result = await _code_finding(index, finding)

    assert result.method == "exact"
    assert result.oifm_id == "OIFM_GMTS_016552"
    assert result.oifm_name == "urinary tract calculus"


@pytest.mark.asyncio
async def test_synonym_match():
    """Finding name matching via synonym."""
    index = AsyncMock()
    index.get = AsyncMock(
        return_value=FakeIndexEntry(
            oifm_id="OIFM_GMTS_016552",
            name="urinary tract calculus",
            synonyms=["kidney stone"],
        )
    )

    finding = _make_finding("kidney stone")
    result = await _code_finding(index, finding)

    assert result.method == "synonym"
    assert result.oifm_id == "OIFM_GMTS_016552"


@pytest.mark.asyncio
async def test_search_match():
    """Finding name resolved via hybrid search."""
    index = AsyncMock()
    index.get = AsyncMock(return_value=None)
    index.search = AsyncMock(
        return_value=[
            FakeIndexEntry(oifm_id="OIFM_GMTS_016552", name="urinary tract calculus"),
            FakeIndexEntry(oifm_id="OIFM_GMTS_020557", name="radiolucent urinary calculus"),
        ]
    )

    finding = _make_finding("urinary calculus")
    result = await _code_finding(index, finding)

    assert result.method == "search"
    assert result.oifm_id == "OIFM_GMTS_016552"
    assert len(result.alternates) == 1
    assert result.alternates[0].oifm_id == "OIFM_GMTS_020557"


@pytest.mark.asyncio
async def test_search_low_confidence_falls_back_to_unresolved():
    """Weak lexical overlap should remain unresolved with deterministic candidates."""
    index = AsyncMock()
    index.get = AsyncMock(return_value=None)
    index.search = AsyncMock(
        return_value=[
            FakeIndexEntry(oifm_id="OIFM_GMTS_016552", name="urinary tract calculus"),
            FakeIndexEntry(oifm_id="OIFM_GMTS_020557", name="radiolucent urinary calculus"),
        ]
    )

    finding = _make_finding("renal stone")
    result = await _code_finding(index, finding)

    assert result.method == "unresolved"
    assert result.oifm_id is None
    assert [c.oifm_id for c in result.alternates] == [
        "OIFM_GMTS_016552",
        "OIFM_GMTS_020557",
    ]


@pytest.mark.asyncio
async def test_unresolved():
    """Finding name with no match at all."""
    index = AsyncMock()
    index.get = AsyncMock(return_value=None)
    index.search = AsyncMock(return_value=[])

    finding = _make_finding("completely made up finding xyz")
    result = await _code_finding(index, finding)

    assert result.method == "unresolved"
    assert result.oifm_id is None


# ---------------------------------------------------------------------------
# _code_location tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_location_coding():
    """Finding with location maps to anatomic RID."""
    loc_index = AsyncMock()
    loc_index.search = AsyncMock(
        return_value=[FakeAnatomicLocation(id="RID205", description="kidney")]
    )

    finding = _make_finding(
        "renal calculus",
        body_region="abdomen",
        specific_anatomy="left kidney",
        laterality="left",
    )
    result = await _code_location(loc_index, finding)

    assert result.location_id == "RID205"
    assert result.location_name == "kidney"
    loc_index.search.assert_called_once_with("left kidney", limit=1, region="Abdomen")


@pytest.mark.asyncio
async def test_location_coding_region_only():
    """Finding with body_region but no specific_anatomy uses region query."""
    loc_index = AsyncMock()
    loc_index.search = AsyncMock(
        return_value=[FakeAnatomicLocation(id="RID56", description="abdomen")]
    )

    finding = _make_finding("ascites", body_region="abdomen")
    result = await _code_location(loc_index, finding)

    assert result.location_id == "RID56"
    loc_index.search.assert_called_once_with("abdomen", limit=1, region="Abdomen")


@pytest.mark.asyncio
async def test_location_coding_unmapped_region_fallback(monkeypatch):
    """Unmapped body regions fall back to unfiltered location search."""
    loc_index = AsyncMock()
    loc_index.search = AsyncMock(
        return_value=[FakeAnatomicLocation(id="RID999", description="custom")]
    )
    monkeypatch.setattr("finding_extractor.coding_bridge._map_location_region", lambda _: None)

    finding = _make_finding("custom", body_region="abdomen")
    result = await _code_location(loc_index, finding)

    assert result.location_id == "RID999"
    loc_index.search.assert_called_once_with("abdomen", limit=1)


@pytest.mark.asyncio
async def test_location_coding_no_location():
    """Finding without location gets empty LocationCoding."""
    loc_index = AsyncMock()

    finding = _make_finding("hepatic steatosis")
    result = await _code_location(loc_index, finding)

    assert result.location_id is None
    assert result.location_name is None
    loc_index.search.assert_not_called()


# ---------------------------------------------------------------------------
# apply_coding tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mixed_findings(monkeypatch):
    """Extraction with mix of resolvable/unresolvable findings."""
    exact_entry = FakeIndexEntry(
        oifm_id="OIFM_GMTS_016552",
        name="urinary tract calculus",
        synonyms=["kidney stone"],
    )
    location_result = FakeAnatomicLocation(id="RID205", description="kidney")

    async def fake_get(name):
        if name == "urinary tract calculus":
            return exact_entry
        return None

    async def fake_search(name, *, limit=10):
        return []

    async def fake_loc_search(query, *, limit=10, region=None):
        if "kidney" in query:
            return [location_result]
        return []

    mock_fm_index = AsyncMock()
    mock_fm_index.get = AsyncMock(side_effect=fake_get)
    mock_fm_index.search = AsyncMock(side_effect=fake_search)

    mock_loc_index = AsyncMock()
    mock_loc_index.search = AsyncMock(side_effect=fake_loc_search)

    _mock_indices(monkeypatch, fm_index=mock_fm_index, loc_index=mock_loc_index)

    extraction = _make_extraction(
        [
            _make_finding(
                "urinary tract calculus", body_region="abdomen", specific_anatomy="left kidney"
            ),
            _make_finding("unknown finding xyz"),
        ]
    )

    result = await apply_coding(extraction)

    assert result.coded_count == 1
    assert result.unresolved_count == 1
    assert result.finding_codings[0].method == "exact"
    assert result.finding_codings[1].method == "unresolved"
    assert result.location_codings[0].location_id == "RID205"
    assert result.location_codings[1].location_id is None
    assert len(result.unresolved) == 1
    assert result.unresolved[0].finding_name == "unknown finding xyz"
    assert result.unresolved[0].reason == "no_match"
    assert result.unresolved[0].candidates == []


@pytest.mark.asyncio
async def test_result_parallel_to_findings(monkeypatch):
    """Codings list length matches findings list length."""
    mock_fm_index = AsyncMock()
    mock_fm_index.get = AsyncMock(return_value=None)
    mock_fm_index.search = AsyncMock(return_value=[])

    mock_loc_index = AsyncMock()
    mock_loc_index.search = AsyncMock(return_value=[])

    _mock_indices(monkeypatch, fm_index=mock_fm_index, loc_index=mock_loc_index)

    findings = [_make_finding(f"finding_{i}") for i in range(5)]
    extraction = _make_extraction(findings)

    result = await apply_coding(extraction)

    assert len(result.finding_codings) == 5
    assert len(result.location_codings) == 5


@pytest.mark.asyncio
async def test_infra_failure_propagates(monkeypatch):
    """Infrastructure failures (index unavailable) propagate to caller."""
    monkeypatch.setattr(
        "finding_extractor.coding_bridge.Index",
        MagicMock(side_effect=RuntimeError("index init failed")),
    )

    extraction = _make_extraction([_make_finding("hepatic steatosis")])

    with pytest.raises(RuntimeError, match="index init failed"):
        await apply_coding(extraction)


@pytest.mark.asyncio
async def test_single_finding_failure_isolated(monkeypatch):
    """One finding failing doesn't block coding of other findings."""
    call_count = 0

    async def flaky_get(name):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise ValueError("transient failure")
        return FakeIndexEntry(oifm_id="OIFM_TEST_000001", name=name)

    mock_fm_index = AsyncMock()
    mock_fm_index.get = AsyncMock(side_effect=flaky_get)

    mock_loc_index = AsyncMock()
    mock_loc_index.search = AsyncMock(return_value=[])

    _mock_indices(monkeypatch, fm_index=mock_fm_index, loc_index=mock_loc_index)

    extraction = _make_extraction(
        [
            _make_finding("will fail"),
            _make_finding("will succeed"),
        ]
    )

    result = await apply_coding(extraction)

    assert result.finding_codings[0].method == "unresolved"
    assert result.finding_codings[1].method == "exact"
    assert result.coded_count == 1
    assert result.unresolved_count == 1
    assert result.unresolved[0].reason == "coding_error"


@pytest.mark.asyncio
async def test_apply_coding_reuses_indexes(monkeypatch):
    """Repeated apply_coding calls reuse already-opened index instances."""
    index_init_calls = 0
    location_init_calls = 0

    mock_fm_index = AsyncMock()
    mock_fm_index.get = AsyncMock(return_value=None)
    mock_fm_index.search = AsyncMock(return_value=[])

    mock_loc_index = AsyncMock()
    mock_loc_index.search = AsyncMock(return_value=[])

    def make_fm_index():
        nonlocal index_init_calls
        index_init_calls += 1
        return mock_fm_index

    def make_loc_index():
        nonlocal location_init_calls
        location_init_calls += 1
        return mock_loc_index

    _mock_indices(monkeypatch, fm_index=mock_fm_index, loc_index=mock_loc_index)
    monkeypatch.setattr("finding_extractor.coding_bridge.Index", make_fm_index)
    monkeypatch.setattr("finding_extractor.coding_bridge.AnatomicLocationIndex", make_loc_index)

    extraction = _make_extraction([_make_finding("finding one"), _make_finding("finding two")])
    await apply_coding(extraction)
    await apply_coding(extraction)

    assert index_init_calls == 1
    assert location_init_calls == 1


@pytest.mark.asyncio
async def test_empty_extraction():
    """Extraction with no findings returns empty result."""
    extraction = _make_extraction([])
    result = await apply_coding(extraction)

    assert result.coded_count == 0
    assert result.unresolved_count == 0
    assert result.finding_codings == []
    assert result.location_codings == []
