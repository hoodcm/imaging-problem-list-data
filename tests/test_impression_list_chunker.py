"""Tests for deterministic impression list chunking."""

from finding_extractor.impression_list_chunker import ImpressionListChunker


def test_numbered_multiline_list_grouped_into_3_then_2():
    text = (
        "Impression:\n"
        "1. No pleural effusion.\n"
        "2. No pneumothorax.\n"
        "3. Stable cardiomediastinal silhouette.\n"
        "4. Mild bibasilar atelectasis.\n"
        "5. No focal consolidation.\n"
    )
    chunker = ImpressionListChunker(max_items_per_chunk=3, min_items_per_chunk=2)
    chunks = chunker.chunk(text)

    assert len(chunks) == 2
    assert "1. No pleural effusion." in chunks[0].text
    assert "3. Stable cardiomediastinal silhouette." in chunks[0].text
    assert "4. Mild bibasilar atelectasis." in chunks[1].text
    assert "5. No focal consolidation." in chunks[1].text


def test_inline_numbered_list_splits():
    text = (
        "Impression: 1. No pleural effusion. 2. No pneumothorax. "
        "3. Stable heart size. 4. Mild bibasilar atelectasis."
    )
    chunker = ImpressionListChunker(max_items_per_chunk=3, min_items_per_chunk=2)
    chunks = chunker.chunk(text)

    assert len(chunks) == 2
    assert "1. No pleural effusion." in chunks[0].text
    assert "2. No pneumothorax." in chunks[0].text
    assert "3. Stable heart size." in chunks[1].text
    assert "4. Mild bibasilar atelectasis." in chunks[1].text


def test_non_list_text_passthrough_single_chunk():
    text = "Impression:\nNo acute cardiopulmonary abnormality."
    chunker = ImpressionListChunker()
    chunks = chunker.chunk(text)

    assert len(chunks) == 1
    assert chunks[0].text == text
