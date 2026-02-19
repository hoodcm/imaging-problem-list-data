"""Tests for the OIFM and anatomic location coding bridge."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from finding_extractor.code_assigner import (
    _code_finding,
    _code_location_with_candidates,
    apply_coding,
    close_reusable_coding_indexes,
)
from finding_extractor.models import (
    AlternateCode,
    ExamInfo,
    ExtractedFinding,
    FindingCode,
    FindingLocation,
    LocationCode,
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
    report_text: str | None = None,
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
        report_text=report_text or f"Test text for {name}.",
    )


def _make_extraction(findings: list[ExtractedFinding]) -> ReportExtraction:
    return ReportExtraction(
        exam_info=ExamInfo(study_description="Test Study"),
        findings=findings,
    )


def _mock_indices(monkeypatch, *, fm_index, loc_index):
    """Wire mock Index and AnatomicLocationIndex into code_assigner."""
    fm_index.__aenter__ = AsyncMock(return_value=fm_index)
    fm_index.__aexit__ = AsyncMock(return_value=False)
    loc_index.__aenter__ = AsyncMock(return_value=loc_index)
    loc_index.__aexit__ = AsyncMock(return_value=False)
    monkeypatch.setattr("finding_extractor.code_assigner.Index", lambda: fm_index)
    monkeypatch.setattr("finding_extractor.code_assigner.AnatomicLocationIndex", lambda: loc_index)


@pytest_asyncio.fixture(autouse=True)
async def _reset_reusable_indexes():
    await close_reusable_coding_indexes()
    yield
    await close_reusable_coding_indexes()


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
    assert len(result.candidates) == 1
    assert result.candidates[0].oifm_id == "OIFM_GMTS_020557"


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
    assert [c.oifm_id for c in result.candidates] == [
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
# _code_location_with_candidates tests
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
    result, query, candidates = await _code_location_with_candidates(loc_index, finding)

    assert result.location_id == "RID205"
    assert result.location_name == "kidney"
    assert query == "left kidney"
    assert candidates == []
    loc_index.search.assert_called_once_with("left kidney", limit=3, region="Abdomen")


@pytest.mark.asyncio
async def test_location_coding_region_only():
    """Finding with body_region but no specific_anatomy uses region query."""
    loc_index = AsyncMock()
    loc_index.search = AsyncMock(
        return_value=[FakeAnatomicLocation(id="RID56", description="abdomen")]
    )

    finding = _make_finding("ascites", body_region="abdomen")
    result, query, candidates = await _code_location_with_candidates(loc_index, finding)

    assert result.location_id == "RID56"
    assert query == "abdomen"
    assert candidates == []
    loc_index.search.assert_called_once_with("abdomen", limit=3, region="Abdomen")


@pytest.mark.asyncio
async def test_location_coding_unmapped_region_fallback(monkeypatch):
    """Unmapped body regions fall back to unfiltered location search."""
    loc_index = AsyncMock()
    loc_index.search = AsyncMock(
        return_value=[FakeAnatomicLocation(id="RID999", description="custom")]
    )
    monkeypatch.setattr("finding_extractor.code_assigner._map_location_region", lambda _: None)

    finding = _make_finding("custom", body_region="abdomen")
    result, query, candidates = await _code_location_with_candidates(loc_index, finding)

    assert result.location_id is None
    assert query == "abdomen"
    assert [c.location_id for c in candidates] == ["RID999"]
    loc_index.search.assert_called_once_with("abdomen", limit=3)


@pytest.mark.asyncio
async def test_location_coding_no_location():
    """Finding without location gets empty LocationCoding."""
    loc_index = AsyncMock()

    finding = _make_finding("hepatic steatosis")
    result, query, candidates = await _code_location_with_candidates(loc_index, finding)

    assert result.location_id is None
    assert result.location_name is None
    assert query is None
    assert candidates == []
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

    first = result.findings[0].coding
    second = result.findings[1].coding
    assert first is not None
    assert second is not None
    assert first.finding_code.method == "exact"
    assert second.finding_code.method == "unresolved"
    assert first.location_code.location_id == "RID205"
    assert second.location_code.location_id is None
    assert second.finding_code.reason == "no_match"
    assert second.finding_code.candidates == []


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

    assert len(result.findings) == 5
    assert all(finding.coding is not None for finding in result.findings)


@pytest.mark.asyncio
async def test_infra_failure_propagates(monkeypatch):
    """Infrastructure failures (index unavailable) propagate to caller."""
    monkeypatch.setattr(
        "finding_extractor.code_assigner.Index",
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

    first = result.findings[0].coding
    second = result.findings[1].coding
    assert first is not None
    assert second is not None
    assert first.finding_code.method == "unresolved"
    assert second.finding_code.method == "exact"
    assert first.finding_code.reason == "coding_error"


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
    monkeypatch.setattr("finding_extractor.code_assigner.Index", make_fm_index)
    monkeypatch.setattr("finding_extractor.code_assigner.AnatomicLocationIndex", make_loc_index)

    extraction = _make_extraction([_make_finding("finding one"), _make_finding("finding two")])
    await apply_coding(extraction)
    await apply_coding(extraction)

    assert index_init_calls == 1
    assert location_init_calls == 1


@pytest.mark.asyncio
async def test_apply_coding_reuses_cached_per_finding_results(monkeypatch):
    """Repeated coding calls for the same finding should hit LRU cache."""
    mock_fm_index = AsyncMock()
    mock_fm_index.get = AsyncMock(
        return_value=FakeIndexEntry(
            oifm_id="OIFM_GMTS_016552",
            name="urinary tract calculus",
        )
    )
    mock_fm_index.search = AsyncMock(return_value=[])

    mock_loc_index = AsyncMock()
    mock_loc_index.search = AsyncMock(
        return_value=[FakeAnatomicLocation(id="RID205", description="kidney")]
    )

    _mock_indices(monkeypatch, fm_index=mock_fm_index, loc_index=mock_loc_index)

    extraction = _make_extraction(
        [
            _make_finding(
                "urinary tract calculus",
                body_region="abdomen",
                specific_anatomy="left kidney",
            )
        ]
    )

    first = await apply_coding(extraction)
    second = await apply_coding(extraction)

    assert first.findings[0].coding is not None
    assert second.findings[0].coding is not None
    assert first.findings[0].coding.finding_code.oifm_id == "OIFM_GMTS_016552"
    assert second.findings[0].coding.finding_code.oifm_id == "OIFM_GMTS_016552"
    assert mock_fm_index.get.call_count == 1
    assert mock_fm_index.search.call_count == 0
    assert mock_loc_index.search.call_count == 1


@pytest.mark.asyncio
async def test_apply_coding_cache_key_includes_evidence_text(monkeypatch):
    """Different evidence text should trigger independent adjudication calls."""
    _mock_indices(monkeypatch, fm_index=AsyncMock(), loc_index=AsyncMock())

    async def fake_code_finding(_index, _finding):
        return FindingCode(
            status="unmapped",
            method="unresolved",
            reason="search_low_confidence",
            candidates=[
                AlternateCode(oifm_id="OIFM_A", name="A"),
                AlternateCode(oifm_id="OIFM_B", name="B"),
            ],
        )

    async def fake_code_location_with_candidates(_loc_index, _finding):
        return (
            LocationCode(status="unmapped", method="unresolved", reason="no_match"),
            None,
            [],
        )

    adjudication_evidence: list[str | None] = []

    async def fake_adjudicate_finding_candidate(**kwargs):
        adjudication_evidence.append(kwargs.get("evidence_text"))
        return SimpleNamespace(unresolved=False, selected_id="OIFM_A")

    monkeypatch.setattr("finding_extractor.code_assigner._code_finding", fake_code_finding)
    monkeypatch.setattr(
        "finding_extractor.code_assigner._code_location_with_candidates",
        fake_code_location_with_candidates,
    )
    monkeypatch.setattr(
        "finding_extractor.code_assigner.adjudicate_finding_candidate",
        fake_adjudicate_finding_candidate,
    )

    extraction_one = _make_extraction(
        [
            _make_finding(
                "vascular calcification",
                body_region="chest",
                report_text="Mild vascular calcification is present.",
            )
        ]
    )
    extraction_two = _make_extraction(
        [
            _make_finding(
                "vascular calcification",
                body_region="chest",
                report_text="Extensive coronary artery calcifications are present.",
            )
        ]
    )

    await apply_coding(
        extraction_one,
        adjudicate_ambiguous=True,
        adjudicator_model="openai:gpt-5-mini",
    )
    await apply_coding(
        extraction_two,
        adjudicate_ambiguous=True,
        adjudicator_model="openai:gpt-5-mini",
    )

    assert adjudication_evidence == [
        "Mild vascular calcification is present.",
        "Extensive coronary artery calcifications are present.",
    ]


@pytest.mark.asyncio
async def test_apply_coding_cache_key_includes_exam_context(monkeypatch):
    """Same finding/evidence in different exam contexts should not reuse adjudication."""
    _mock_indices(monkeypatch, fm_index=AsyncMock(), loc_index=AsyncMock())

    async def fake_code_finding(_index, _finding):
        return FindingCode(
            status="unmapped",
            method="unresolved",
            reason="search_low_confidence",
            candidates=[
                AlternateCode(oifm_id="OIFM_A", name="A"),
                AlternateCode(oifm_id="OIFM_B", name="B"),
            ],
        )

    async def fake_code_location_with_candidates(_loc_index, _finding):
        return (
            LocationCode(status="unmapped", method="unresolved", reason="no_match"),
            None,
            [],
        )

    adjudication_exam_context: list[tuple[str | None, str | None, str | None]] = []

    async def fake_adjudicate_finding_candidate(**kwargs):
        adjudication_exam_context.append(
            (
                kwargs.get("exam_modality"),
                kwargs.get("exam_body_part"),
                kwargs.get("exam_laterality"),
            )
        )
        return SimpleNamespace(unresolved=False, selected_id="OIFM_A")

    monkeypatch.setattr("finding_extractor.code_assigner._code_finding", fake_code_finding)
    monkeypatch.setattr(
        "finding_extractor.code_assigner._code_location_with_candidates",
        fake_code_location_with_candidates,
    )
    monkeypatch.setattr(
        "finding_extractor.code_assigner.adjudicate_finding_candidate",
        fake_adjudicate_finding_candidate,
    )

    finding = _make_finding(
        "vascular calcification",
        body_region="chest",
        report_text="Vascular calcifications are present.",
    )

    extraction = _make_extraction([finding])

    await apply_coding(
        extraction,
        adjudicate_ambiguous=True,
        adjudicator_model="openai:gpt-5-mini",
        exam_info=ExamInfo(
            study_description="CT Chest",
            modality="CT",
            body_part="chest",
            laterality=None,
        ),
    )
    await apply_coding(
        extraction,
        adjudicate_ambiguous=True,
        adjudicator_model="openai:gpt-5-mini",
        exam_info=ExamInfo(
            study_description="XR Chest",
            modality="XR",
            body_part="chest",
            laterality=None,
        ),
    )

    assert adjudication_exam_context == [
        ("CT", "chest", None),
        ("XR", "chest", None),
    ]


@pytest.mark.asyncio
async def test_apply_coding_concurrent_calls_share_single_index_init(monkeypatch):
    """Overlapping apply_coding calls should initialize shared indexes only once."""
    index_init_calls = 0
    location_init_calls = 0

    async def slow_get(_name):
        await asyncio.sleep(0.005)
        return None

    async def slow_search(*_args, **_kwargs):
        await asyncio.sleep(0.005)
        return []

    mock_fm_index = AsyncMock()
    mock_fm_index.get = AsyncMock(side_effect=slow_get)
    mock_fm_index.search = AsyncMock(side_effect=slow_search)

    mock_loc_index = AsyncMock()
    mock_loc_index.search = AsyncMock(side_effect=slow_search)

    def make_fm_index():
        nonlocal index_init_calls
        index_init_calls += 1
        return mock_fm_index

    def make_loc_index():
        nonlocal location_init_calls
        location_init_calls += 1
        return mock_loc_index

    _mock_indices(monkeypatch, fm_index=mock_fm_index, loc_index=mock_loc_index)
    monkeypatch.setattr("finding_extractor.code_assigner.Index", make_fm_index)
    monkeypatch.setattr("finding_extractor.code_assigner.AnatomicLocationIndex", make_loc_index)

    extraction = _make_extraction([_make_finding("finding one"), _make_finding("finding two")])
    results = await asyncio.gather(*[apply_coding(extraction) for _ in range(6)])

    assert index_init_calls == 1
    assert location_init_calls == 1
    assert all(len(result.findings) == 2 for result in results)
    assert all(
        finding.coding is not None and finding.coding.finding_code.status == "unmapped"
        for result in results
        for finding in result.findings
    )


@pytest.mark.asyncio
async def test_apply_coding_serializes_shared_index_access(monkeypatch):
    """Concurrent coding must not overlap calls on shared index connections."""
    fm_in_flight = 0
    fm_max_in_flight = 0
    loc_in_flight = 0
    loc_max_in_flight = 0

    async def tracked_fm_get(_name):
        nonlocal fm_in_flight, fm_max_in_flight
        fm_in_flight += 1
        fm_max_in_flight = max(fm_max_in_flight, fm_in_flight)
        await asyncio.sleep(0.01)
        fm_in_flight -= 1
        return None

    async def tracked_fm_search(*_args, **_kwargs):
        nonlocal fm_in_flight, fm_max_in_flight
        fm_in_flight += 1
        fm_max_in_flight = max(fm_max_in_flight, fm_in_flight)
        await asyncio.sleep(0.01)
        fm_in_flight -= 1
        return []

    async def tracked_loc_search(*_args, **_kwargs):
        nonlocal loc_in_flight, loc_max_in_flight
        loc_in_flight += 1
        loc_max_in_flight = max(loc_max_in_flight, loc_in_flight)
        await asyncio.sleep(0.01)
        loc_in_flight -= 1
        return []

    mock_fm_index = AsyncMock()
    mock_fm_index.get = AsyncMock(side_effect=tracked_fm_get)
    mock_fm_index.search = AsyncMock(side_effect=tracked_fm_search)

    mock_loc_index = AsyncMock()
    mock_loc_index.search = AsyncMock(side_effect=tracked_loc_search)

    _mock_indices(monkeypatch, fm_index=mock_fm_index, loc_index=mock_loc_index)

    extraction = _make_extraction(
        [
            _make_finding(
                f"finding_{i}",
                body_region="abdomen",
                specific_anatomy="left kidney",
            )
            for i in range(6)
        ]
    )
    await apply_coding(extraction, max_concurrency=6)

    assert fm_max_in_flight == 1
    assert loc_max_in_flight == 1


@pytest.mark.asyncio
async def test_close_reusable_indexes_forces_reinitialization(monkeypatch):
    """Lifecycle cleanup should close shared indexes and force clean re-init."""
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
    monkeypatch.setattr("finding_extractor.code_assigner.Index", make_fm_index)
    monkeypatch.setattr("finding_extractor.code_assigner.AnatomicLocationIndex", make_loc_index)

    extraction = _make_extraction([_make_finding("finding one")])
    await apply_coding(extraction)
    await close_reusable_coding_indexes()
    await apply_coding(extraction)

    assert index_init_calls == 2
    assert location_init_calls == 2


@pytest.mark.asyncio
async def test_empty_extraction():
    """Extraction with no findings returns empty result."""
    extraction = _make_extraction([])
    result = await apply_coding(extraction)

    assert result.findings == []
