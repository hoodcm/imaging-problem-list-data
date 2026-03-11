"""Small shared helpers for runtime budget preflight checks."""

from __future__ import annotations

import math

DEFAULT_MAX_PREDICTED_RUNTIME_SECONDS = 15 * 60


def format_duration_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, rem = divmod(seconds, 60)
    return f"{minutes}m" if rem == 0 else f"{minutes}m{rem}s"


def estimate_runtime_upper_bound_seconds(
    *,
    item_count: int,
    workers: int,
    timeout_seconds: int,
    retries: int,
) -> int:
    if item_count <= 0:
        return 0
    return math.ceil(item_count / workers) * timeout_seconds * (retries + 1)


def build_runtime_preflight(
    *,
    command_label: str,
    item_label: str,
    item_count: int,
    workers: int,
    timeout_seconds: int,
    retries: int,
    budget_seconds: int,
    allow_slow: bool,
) -> tuple[str, str | None, str | None]:
    """Return (preflight_line, error_message, warning_message)."""
    predicted_seconds = estimate_runtime_upper_bound_seconds(
        item_count=item_count,
        workers=workers,
        timeout_seconds=timeout_seconds,
        retries=retries,
    )
    predicted_text = format_duration_seconds(predicted_seconds)
    budget_text = format_duration_seconds(budget_seconds)
    line = (
        f"{command_label} preflight: {item_label}={item_count} "
        f"workers={workers} timeout={timeout_seconds}s retries={retries} "
        f"predicted_upper_bound={predicted_text} budget={budget_text}"
    )
    if predicted_seconds <= budget_seconds:
        return line, None, None
    if allow_slow:
        return (
            line,
            None,
            f"{command_label} preflight warning: running despite high predicted bound ({predicted_text}).",
        )
    return (
        line,
        (
            "Predicted runtime upper bound exceeds fail-fast budget. "
            f"predicted={predicted_text}, budget={budget_text}. "
            "Adjust workers/timeout/retries, raise --max-predicted-runtime-seconds, "
            "or pass --allow-slow."
        ),
        None,
    )

