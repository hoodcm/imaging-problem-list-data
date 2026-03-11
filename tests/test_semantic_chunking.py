"""Tests for deterministic sentence-first semantic chunking."""

import pytest

from finding_extractor.extractor.chunking import (
    ChunkingSettings,
    SectionChunk,
    _group_sentence_spans,
    _normalize_chunks,
    chunk_section_text,
)


def test_normalize_chunks_rejects_non_whitespace_gap():
    text = "Alpha. Beta."
    chunks = [
        SectionChunk(start_index=0, end_index=5, text="Alpha"),
        SectionChunk(start_index=7, end_index=12, text="Beta."),
    ]

    with pytest.raises(ValueError, match="non-whitespace gap"):
        _normalize_chunks(chunks, text)


@pytest.mark.asyncio
async def test_chunk_section_text_non_target_section_passthrough():
    result = await chunk_section_text(
        section_name="technique",
        section_text="Technique: CT without contrast.",
        settings=ChunkingSettings(),
    )

    assert len(result.chunks) == 1
    assert result.diagnostics.strategy == "non_target_section_passthrough"
    assert result.diagnostics.semantic_applied is False


@pytest.mark.asyncio
async def test_chunk_section_text_below_threshold_passthrough(monkeypatch):
    sentence_spans = (
        SectionChunk(start_index=0, end_index=6, text="A. B. "),
        SectionChunk(start_index=6, end_index=8, text="C."),
    )
    monkeypatch.setattr(
        "finding_extractor.extractor.chunking._sentence_spans",
        lambda _text: sentence_spans,
    )

    result = await chunk_section_text(
        section_name="findings",
        section_text="A. B. C.",
        settings=ChunkingSettings(semantic_trigger_sentence_count=4),
    )

    assert [chunk.text for chunk in result.chunks] == ["A. B. C."]
    assert result.diagnostics.strategy == "below_threshold_passthrough"
    assert result.diagnostics.sentence_count == 2
    assert result.diagnostics.semantic_applied is False


@pytest.mark.asyncio
async def test_chunk_section_text_uses_semantic_for_larger_sections(monkeypatch):
    sentence_spans = (
        SectionChunk(start_index=0, end_index=3, text="A. "),
        SectionChunk(start_index=3, end_index=6, text="B. "),
        SectionChunk(start_index=6, end_index=9, text="C. "),
        SectionChunk(start_index=9, end_index=12, text="D. "),
        SectionChunk(start_index=12, end_index=14, text="E."),
    )
    semantic_chunks = (
        SectionChunk(start_index=0, end_index=9, text="A. B. C. "),
        SectionChunk(start_index=9, end_index=14, text="D. E."),
    )
    monkeypatch.setattr(
        "finding_extractor.extractor.chunking._sentence_spans",
        lambda _text: sentence_spans,
    )
    monkeypatch.setattr(
        "finding_extractor.extractor.chunking._semantic_candidates",
        lambda _text, _settings: semantic_chunks,
    )

    result = await chunk_section_text(
        section_name="impression",
        section_text="A. B. C. D. E.",
        settings=ChunkingSettings(semantic_trigger_sentence_count=4),
    )

    assert [chunk.text for chunk in result.chunks] == ["A. B. C. ", "D. E."]
    assert result.diagnostics.strategy == "impression_semantic_grouped"
    assert result.diagnostics.sentence_count == 5
    assert result.diagnostics.semantic_applied is True


@pytest.mark.asyncio
async def test_chunk_section_text_falls_back_to_sentences_when_semantic_fails(monkeypatch):
    sentence_spans = (
        SectionChunk(start_index=0, end_index=3, text="A. "),
        SectionChunk(start_index=3, end_index=6, text="B. "),
        SectionChunk(start_index=6, end_index=9, text="C. "),
        SectionChunk(start_index=9, end_index=12, text="D. "),
        SectionChunk(start_index=12, end_index=14, text="E."),
    )
    monkeypatch.setattr(
        "finding_extractor.extractor.chunking._sentence_spans",
        lambda _text: sentence_spans,
    )

    def _raise_semantic(_text, _settings):
        raise RuntimeError("semantic unavailable")

    monkeypatch.setattr(
        "finding_extractor.extractor.chunking._semantic_candidates",
        _raise_semantic,
    )

    result = await chunk_section_text(
        section_name="findings",
        section_text="A. B. C. D. E.",
        settings=ChunkingSettings(semantic_trigger_sentence_count=4),
    )

    assert [chunk.text for chunk in result.chunks] == ["A. B. C. ", "D. E."]
    assert result.diagnostics.strategy == "semantic_failed_sentence_fallback"
    assert result.diagnostics.semantic_applied is False
    assert result.diagnostics.warnings == ("semantic_error:RuntimeError",)


@pytest.mark.asyncio
async def test_chunk_section_text_impression_below_threshold_passthrough(monkeypatch):
    sentence_spans = (
        SectionChunk(start_index=0, end_index=3, text="A. "),
        SectionChunk(start_index=3, end_index=5, text="B."),
    )
    semantic_chunks = (SectionChunk(start_index=0, end_index=5, text="A. B."),)
    semantic_called = False

    monkeypatch.setattr(
        "finding_extractor.extractor.chunking._sentence_spans",
        lambda _text: sentence_spans,
    )

    def _semantic(_text, _settings):
        nonlocal semantic_called
        semantic_called = True
        return semantic_chunks

    monkeypatch.setattr("finding_extractor.extractor.chunking._semantic_candidates", _semantic)

    result = await chunk_section_text(
        section_name="impression",
        section_text="A. B.",
        settings=ChunkingSettings(semantic_trigger_sentence_count=99),
    )

    assert semantic_called is False
    assert [chunk.text for chunk in result.chunks] == ["A. B."]
    assert result.diagnostics.strategy == "below_threshold_passthrough"
    assert result.diagnostics.semantic_applied is False


@pytest.mark.asyncio
async def test_chunk_section_text_impression_list_respects_threshold_passthrough():
    section_text = "Impression:\n1. No pleural effusion.\n2. No pneumothorax.\n"
    result = await chunk_section_text(
        section_name="impression",
        section_text=section_text,
        settings=ChunkingSettings(semantic_trigger_sentence_count=4),
    )

    assert len(result.chunks) == 1
    assert result.chunks[0].text == "1. No pleural effusion.\n2. No pneumothorax.\n"
    assert result.diagnostics.strategy == "below_threshold_passthrough"


@pytest.mark.asyncio
async def test_chunk_section_text_uses_impression_list_grouping_before_semantic(monkeypatch):
    semantic_called = False

    def _semantic_candidates(_text, _settings):
        nonlocal semantic_called
        semantic_called = True
        return ()

    monkeypatch.setattr(
        "finding_extractor.extractor.chunking._semantic_candidates",
        _semantic_candidates,
    )

    section_text = (
        "Impression:\n"
        "1. No pleural effusion.\n"
        "2. No pneumothorax.\n"
        "3. Stable cardiomediastinal silhouette.\n"
        "4. Mild bibasilar atelectasis.\n"
        "5. No focal consolidation.\n"
    )
    result = await chunk_section_text(
        section_name="impression",
        section_text=section_text,
        settings=ChunkingSettings(semantic_trigger_sentence_count=1),
    )

    assert len(result.chunks) == 2
    assert result.diagnostics.strategy == "impression_list_grouped"
    assert result.diagnostics.semantic_applied is False
    assert semantic_called is False
    assert "1. No pleural effusion." in result.chunks[0].text
    assert "5. No focal consolidation." in result.chunks[1].text
    assert not result.chunks[0].text.lstrip().lower().startswith("impression:")


@pytest.mark.asyncio
async def test_chunk_section_text_strips_leading_findings_header_in_passthrough():
    section_text = "Findings:\nNo pleural effusion."
    result = await chunk_section_text(
        section_name="findings",
        section_text=section_text,
        settings=ChunkingSettings(semantic_trigger_sentence_count=4),
    )

    assert len(result.chunks) == 1
    assert result.diagnostics.strategy == "below_threshold_passthrough"
    assert result.chunks[0].text == "No pleural effusion."


@pytest.mark.asyncio
async def test_chunk_section_text_strips_leading_body_alias_header():
    section_text = "Body:\nNo focal airspace opacity."
    result = await chunk_section_text(
        section_name="findings",
        section_text=section_text,
        settings=ChunkingSettings(semantic_trigger_sentence_count=4),
    )

    assert len(result.chunks) == 1
    assert result.diagnostics.strategy == "below_threshold_passthrough"
    assert result.chunks[0].text == "No focal airspace opacity."


def test_group_sentence_spans_avoids_trailing_singleton():
    section_text = "A. B. C. D."
    sentence_spans = (
        SectionChunk(start_index=0, end_index=3, text="A. "),
        SectionChunk(start_index=3, end_index=6, text="B. "),
        SectionChunk(start_index=6, end_index=9, text="C. "),
        SectionChunk(start_index=9, end_index=11, text="D."),
    )

    grouped = _group_sentence_spans(
        sentence_spans,
        section_text,
        max_sentences_per_chunk=3,
    )

    assert [chunk.text for chunk in grouped] == ["A. B. ", "C. D."]
