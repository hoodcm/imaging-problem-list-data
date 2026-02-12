"""Tests for structured logging bootstrap."""

import logging
from typing import cast

import pytest
import structlog
from structlog.stdlib import ProcessorFormatter

from finding_extractor import logging_setup
from finding_extractor.config import Settings


@pytest.fixture
def _restore_logging_state(monkeypatch):
    """Restore global logging/structlog state after each test."""
    root_logger = logging.getLogger()
    original_handlers = root_logger.handlers.copy()
    original_level = root_logger.level
    original_propagate = root_logger.propagate

    monkeypatch.setattr(logging_setup, "_configured", False)
    root_logger.handlers = []

    yield root_logger

    root_logger.handlers = original_handlers
    root_logger.setLevel(original_level)
    root_logger.propagate = original_propagate
    structlog.reset_defaults()
    monkeypatch.setattr(logging_setup, "_configured", False)


def test_setup_logging_is_idempotent(_restore_logging_state):
    """Repeated setup calls should not duplicate root handlers."""
    root_logger = _restore_logging_state
    settings = Settings(log_level="DEBUG", log_json=False)

    logging_setup.setup_logging(settings, include_logfire_processor=False)
    first_handler = root_logger.handlers[0]

    logging_setup.setup_logging(settings, include_logfire_processor=False)

    assert len(root_logger.handlers) == 1
    assert root_logger.handlers[0] is first_handler
    assert root_logger.level == logging.DEBUG


def test_setup_logging_switches_renderer_by_config(_restore_logging_state):
    """Renderer should be JSON in JSON mode and Console otherwise."""
    root_logger = _restore_logging_state

    json_settings = Settings(log_level="INFO", log_json=True)
    logging_setup.setup_logging(json_settings, include_logfire_processor=False)

    json_formatter = root_logger.handlers[0].formatter
    assert json_formatter is not None
    assert type(json_formatter.processors[-1]).__name__ == "JSONRenderer"


@pytest.mark.usefixtures("_restore_logging_state")
def test_setup_logging_includes_logfire_processor_when_requested(monkeypatch):
    """Optional Logfire processor should be included when requested."""
    settings = Settings(log_level="INFO", log_json=False)

    logging_setup.setup_logging(settings, include_logfire_processor=True)

    formatter = cast(ProcessorFormatter, logging.getLogger().handlers[0].formatter)
    processor_names = [type(processor).__name__ for processor in formatter.processors]
    assert any("logfire" in name.lower() for name in processor_names)
