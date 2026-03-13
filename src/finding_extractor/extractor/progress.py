"""Progress callback types and helpers for the extraction pipeline."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Protocol, runtime_checkable


@runtime_checkable
class ProgressCallback(Protocol):
    """Async callback for reporting extraction pipeline progress."""

    async def __call__(self, message: str) -> None: ...


# Type alias kept for use in function signatures where ty/mypy struggle
# to match async functions against Protocol.__call__.  The Protocol above
# is the canonical description; this alias is structurally equivalent.
ProgressCallbackType = Callable[[str], Awaitable[None]]


def format_stage_status(stage: str, detail: str) -> str:
    """Return a parseable stage status message."""
    return f"[stage:{stage}] {detail}"


async def emit_stage_progress(
    callback: ProgressCallbackType | None, stage: str, detail: str
) -> None:
    """Emit a structured stage progress message if callback is provided."""
    if callback is not None:
        await callback(format_stage_status(stage, detail))
