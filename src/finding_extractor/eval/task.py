"""Task function adapter wrapping shared orchestrated runtime for pydantic-evals."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from finding_extractor.eval.models import EvalInput
from finding_extractor.models import ExtractedReportFindings


def make_eval_task(
    model: str,
    reasoning: str | None = None,
    timeout_seconds: int = 120,
) -> Callable[[EvalInput], Awaitable[ExtractedReportFindings]]:
    """Create an async task function for pydantic-evals evaluation.

    The returned function wraps the shared extraction runtime with a per-case timeout.

    Args:
        model: Model identifier for extraction.
        reasoning: Optional reasoning level override.
        timeout_seconds: Per-case timeout in seconds.

    Returns:
        Async function mapping EvalInput -> ExtractedReportFindings.
    """

    async def task(inputs: EvalInput) -> ExtractedReportFindings:
        from finding_extractor.extractor.runtime import run_extraction_runtime

        runtime_result = await asyncio.wait_for(
            run_extraction_runtime(
                report_text=inputs.report_text,
                study_description=inputs.study_description,
                model=model,
                reasoning=reasoning,
                validate=False,
                reliability_mode="strict",
                store=None,
                db_path=None,
                source_ref=None,
                report_id=None,
                status_callback=None,
            ),
            timeout=timeout_seconds,
        )
        return runtime_result.extraction

    return task
