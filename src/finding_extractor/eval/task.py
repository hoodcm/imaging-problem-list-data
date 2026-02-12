"""Task function adapter wrapping extract_findings() for pydantic-evals."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from finding_extractor.eval.models import EvalInput
from finding_extractor.models import ReportExtraction


def make_eval_task(
    model: str,
    reasoning: str | None = None,
    timeout_seconds: int = 120,
) -> Callable[[EvalInput], Awaitable[ReportExtraction]]:
    """Create an async task function for pydantic-evals evaluation.

    The returned function wraps extract_findings() with a per-case timeout.

    Args:
        model: Model identifier for extraction.
        reasoning: Optional reasoning level override.
        timeout_seconds: Per-case timeout in seconds.

    Returns:
        Async function mapping EvalInput -> ReportExtraction.
    """

    async def task(inputs: EvalInput) -> ReportExtraction:
        from finding_extractor.agent import extract_findings

        result = await asyncio.wait_for(
            extract_findings(
                report_text=inputs.report_text,
                exam_description=inputs.exam_description,
                model=model,
                reasoning=reasoning,
            ),
            timeout=timeout_seconds,
        )
        return result.extraction

    return task
