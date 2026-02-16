"""Deterministic impression list chunker built on Chonkie BaseChunker."""

from __future__ import annotations

import re

from chonkie.chunker.base import BaseChunker
from chonkie.types import Chunk

_RE_LIST_MARKER_LINE = re.compile(
    r"(?m)^[ \t]*(?:[-*•]|(?:\d{1,3}|[ivxlcdm]+|[A-Za-z])[.)])\s+"
)
_RE_LIST_MARKER_INLINE = re.compile(
    r"(?<!\w)(?:\d{1,3}|[ivxlcdm]+|[A-Za-z])[.)]\s+"
)


def _passthrough_chunk(text: str, chunker: BaseChunker) -> Chunk:
    return Chunk(
        text=text,
        start_index=0,
        end_index=len(text),
        token_count=chunker.tokenizer.count_tokens(text),
    )


def _group_item_count_spans(
    item_spans: list[tuple[int, int]],
    *,
    max_items_per_chunk: int,
    min_items_per_chunk: int,
) -> list[tuple[int, int]]:
    """Group list item spans into chunk index ranges."""
    groups: list[tuple[int, int]] = []
    i = 0
    total = len(item_spans)
    while i < total:
        remaining = total - i
        if remaining <= max_items_per_chunk:
            take = remaining
        else:
            take = max_items_per_chunk
            # Prefer 2+2 over 3+1 where possible.
            if remaining - take == 1 and max_items_per_chunk > min_items_per_chunk:
                take = max_items_per_chunk - 1
        groups.append((i, i + take - 1))
        i += take
    return groups


class ImpressionListChunker(BaseChunker):
    """Chunk numbered/bulleted impression lists into 2-3 item groups."""

    def __init__(
        self,
        *,
        max_items_per_chunk: int = 3,
        min_items_per_chunk: int = 2,
        tokenizer: str = "character",
    ) -> None:
        super().__init__(tokenizer=tokenizer)
        self.max_items_per_chunk = max(1, max_items_per_chunk)
        self.min_items_per_chunk = max(
            1, min(min_items_per_chunk, self.max_items_per_chunk)
        )

    def _collect_item_starts(self, text: str) -> list[int]:
        line_starts = [match.start() for match in _RE_LIST_MARKER_LINE.finditer(text)]
        if len(line_starts) >= 2:
            return sorted(set(line_starts))

        inline_starts = [match.start() for match in _RE_LIST_MARKER_INLINE.finditer(text)]
        if len(inline_starts) < 2:
            return []

        prefix = text[: inline_starts[0]].lower()
        if (
            "impression" in prefix
            or "conclusion" in prefix
            or "findings/impression" in prefix
            or ":" in prefix
        ):
            return sorted(set(inline_starts))
        return []

    def _item_spans(self, text: str) -> list[tuple[int, int]]:
        starts = self._collect_item_starts(text)
        if len(starts) < 2:
            return []

        spans: list[tuple[int, int]] = []
        for i, start in enumerate(starts):
            end = starts[i + 1] if i + 1 < len(starts) else len(text)
            if start >= end:
                continue
            item_text = text[start:end].strip()
            if not item_text or not re.search(r"[A-Za-z]", item_text):
                continue
            spans.append((start, end))
        return spans if len(spans) >= 2 else []

    def chunk(self, text: str) -> list[Chunk]:
        if not text:
            return []

        item_spans = self._item_spans(text)
        if len(item_spans) < 2:
            return [_passthrough_chunk(text, self)]

        grouped_item_ranges = _group_item_count_spans(
            item_spans,
            max_items_per_chunk=self.max_items_per_chunk,
            min_items_per_chunk=self.min_items_per_chunk,
        )

        chunks: list[Chunk] = []
        for group_idx, (start_item_idx, end_item_idx) in enumerate(grouped_item_ranges):
            start = item_spans[start_item_idx][0]
            end = item_spans[end_item_idx][1]
            if group_idx == 0:
                start = 0

            chunk_text = text[start:end]
            if not chunk_text:
                continue
            chunks.append(
                Chunk(
                    text=chunk_text,
                    start_index=start,
                    end_index=end,
                    token_count=self.tokenizer.count_tokens(chunk_text),
                )
            )

        if not chunks:
            return [_passthrough_chunk(text, self)]
        return chunks
