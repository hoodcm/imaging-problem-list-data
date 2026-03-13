"""Test configuration and fixtures."""

from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from click.testing import CliRunner
from pydantic_ai.models import override_allow_model_requests
from structlog.contextvars import get_contextvars

from alembic import command
from finding_extractor.core.config import clear_settings_cache
from finding_extractor.db.store import ExtractionStore

_ALEMBIC_INI_PATH = Path(__file__).resolve().parents[1] / "alembic.ini"


@pytest.fixture(autouse=True)
def _clear_cached_settings() -> Iterator[None]:
    """Ensure env var mutations in tests do not leak through the settings cache."""
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.fixture(autouse=True)
def _block_model_requests(request: pytest.FixtureRequest) -> Iterator[None]:
    """Block real model requests in tests unless explicitly integration-marked."""
    if request.node.get_closest_marker("integration") is not None:
        yield
        return
    with override_allow_model_requests(False):
        yield


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

    def warning(self, event: str, **kwargs: Any) -> None:
        self.records.append(
            {
                "level": "warning",
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


class RuntimeLoggingSpy:
    """Capture runtime logging bootstrap calls across startup tests."""

    def __init__(self) -> None:
        self.configure_calls: list[dict[str, Any]] = []
        self.setup_calls: list[dict[str, Any]] = []

    def patch(
        self,
        monkeypatch: pytest.MonkeyPatch,
        module_path: str,
        *,
        logfire_enabled: bool,
    ) -> None:
        def fake_configure_logfire(*, runtime, enabled_override=None, fastapi_app=None):
            self.configure_calls.append(
                {
                    "runtime": runtime,
                    "enabled_override": enabled_override,
                    "fastapi_app": fastapi_app,
                }
            )
            return logfire_enabled

        def fake_setup_logging(settings, *, include_logfire_processor):
            self.setup_calls.append(
                {
                    "settings": settings,
                    "include_logfire_processor": include_logfire_processor,
                }
            )

        monkeypatch.setattr(f"{module_path}.configure_logfire", fake_configure_logfire)
        monkeypatch.setattr(f"{module_path}.setup_logging", fake_setup_logging)


@pytest.fixture
def context_capture_logger() -> ContextCaptureLogger:
    """Provide a fresh structured log capture helper per test."""
    return ContextCaptureLogger()


@pytest.fixture
def cli_runner() -> CliRunner:
    """Provide a shared Click runner for CLI-oriented tests."""
    return CliRunner()


@pytest.fixture
def store_factory(monkeypatch: pytest.MonkeyPatch):
    """Create initialized ExtractionStore instances with managed cleanup."""

    @asynccontextmanager
    async def _store_factory(db_path: Path):
        monkeypatch.setenv("IPL_DB_PATH", str(db_path))
        command.upgrade(Config(str(_ALEMBIC_INI_PATH)), "head")
        store = ExtractionStore(db_path)
        await store.init()
        try:
            yield store
        finally:
            await store.close()

    return _store_factory


@pytest.fixture
def runtime_logging_spy() -> RuntimeLoggingSpy:
    """Provide helper for patching and asserting startup logging wiring."""
    return RuntimeLoggingSpy()
