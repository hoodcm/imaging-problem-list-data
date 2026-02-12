"""Test configuration and fixtures."""

from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner
from structlog.contextvars import get_contextvars

from finding_extractor.config import clear_settings_cache
from finding_extractor.store import ExtractionStore


@pytest.fixture(autouse=True)
def _clear_cached_settings() -> Iterator[None]:
    """Ensure env var mutations in tests do not leak through the settings cache."""
    clear_settings_cache()
    yield
    clear_settings_cache()


class ContextCaptureLogger:
    """Capture event kwargs and active structlog contextvars."""

    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def info(self, event: str, **kwargs: Any) -> None:
        self.records.append(
            {"level": "info", "event": event, "kwargs": kwargs, "context": dict(get_contextvars())}
        )

    def debug(self, event: str, **kwargs: Any) -> None:
        self.records.append(
            {
                "level": "debug",
                "event": event,
                "kwargs": kwargs,
                "context": dict(get_contextvars()),
            }
        )

    def exception(self, event: str, **kwargs: Any) -> None:
        self.records.append(
            {
                "level": "exception",
                "event": event,
                "kwargs": kwargs,
                "context": dict(get_contextvars()),
            }
        )


@pytest.fixture
def context_capture_logger() -> ContextCaptureLogger:
    """Provide a fresh structured log capture helper per test."""
    return ContextCaptureLogger()


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a shared Click runner for CLI-oriented tests."""
    return CliRunner()


@pytest.fixture
def store_factory():
    """Create initialized ExtractionStore instances with managed cleanup."""

    @asynccontextmanager
    async def _store_factory(db_path: Path):
        store = ExtractionStore(db_path)
        await store.init()
        try:
            yield store
        finally:
            await store.close()

    return _store_factory
