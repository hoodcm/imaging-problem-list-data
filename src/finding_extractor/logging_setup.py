"""Centralized structured logging setup shared across runtimes."""

from __future__ import annotations

import logging
import threading

import structlog

from finding_extractor.config import Settings

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_configured = False


def _build_renderer(settings: Settings) -> structlog.types.Processor:
    if settings.log_json:
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=False)


def _get_logfire_processor() -> structlog.types.Processor | None:
    try:
        import logfire
    except Exception:
        logger.exception("Logfire processor requested but import failed")
        return None

    return logfire.StructlogProcessor()


def setup_logging(settings: Settings, *, include_logfire_processor: bool) -> None:
    """Configure process-global structured logging once."""
    global _configured

    with _lock:
        if _configured:
            return

        shared_processors: list[structlog.types.Processor] = [
            structlog.contextvars.merge_contextvars,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=True),
            structlog.processors.StackInfoRenderer(),
        ]

        structlog.configure(
            processors=[
                *shared_processors,
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        formatter_processors: list[structlog.types.Processor] = []
        if include_logfire_processor:
            logfire_processor = _get_logfire_processor()
            if logfire_processor is not None:
                formatter_processors.append(logfire_processor)

        if settings.log_json:
            formatter_processors.append(structlog.processors.format_exc_info)

        formatter_processors.extend(
            [
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                _build_renderer(settings),
            ]
        )

        handler = logging.StreamHandler()
        handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=shared_processors,
                processors=formatter_processors,
            )
        )

        root_logger = logging.getLogger()
        root_logger.handlers = [handler]
        root_logger.setLevel(settings.log_level)

        _configured = True
