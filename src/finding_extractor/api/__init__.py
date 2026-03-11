"""FastAPI application factory and server entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import structlog
import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

from finding_extractor.api.routes import router as api_router
from finding_extractor.core.config import get_settings
from finding_extractor.core.logging_setup import setup_logging
from finding_extractor.core.observability import configure_logfire, get_current_trace_id
from finding_extractor.db.store import ExtractionStore
from finding_extractor.llm.catalog import ModelCatalogService
from finding_extractor.worker.extraction_jobs import register_run_extraction_task, run_extraction

logger = structlog.get_logger(__name__)


def _get_active_trace_context() -> dict[str, str]:
    """Return trace/span ids from active OpenTelemetry span when available."""
    trace_id = get_current_trace_id()
    if trace_id is None:
        return {}

    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        span_context = span.get_span_context()
        if span_context.is_valid:
            return {
                "trace_id": trace_id,
                "span_id": f"{span_context.span_id:016x}",
            }
    except Exception:
        pass
    return {"trace_id": trace_id}


def create_app(store: ExtractionStore | None = None, broker: Any = None) -> FastAPI:
    """Create FastAPI app with injectable store/broker for tests."""
    settings = get_settings()
    uses_custom_broker = broker is not None
    if broker is None:
        from finding_extractor.worker.broker import broker as default_broker

        broker = default_broker

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logger.info("API lifespan startup begin")
        app.state.store = store or ExtractionStore(settings.db_path)
        app.state.broker = broker
        app.state.model_catalog = ModelCatalogService(settings)
        app.state.run_extraction_task = (
            register_run_extraction_task(app.state.broker) if uses_custom_broker else run_extraction
        )
        await app.state.store.init()
        await app.state.store.create_user("talkasab", "Tarik Alkasab", "tarik@alkasab.org")
        if not app.state.broker.is_worker_process:
            await app.state.broker.startup()
        logger.info(
            "API lifespan startup complete",
            uses_custom_broker=uses_custom_broker,
        )
        try:
            yield
        finally:
            logger.info("API lifespan shutdown begin")
            if not app.state.broker.is_worker_process:
                await app.state.broker.shutdown()
            await app.state.model_catalog.close()
            await app.state.store.close()
            logger.info("API lifespan shutdown complete")

    app = FastAPI(title="Finding Extractor API", version="0.1.0", lifespan=lifespan)
    logfire_enabled = configure_logfire(runtime="api", fastapi_app=app)
    setup_logging(settings, include_logfire_processor=logfire_enabled)
    cors_origins = settings.cors_origins
    app.add_middleware(
        CORSMiddleware,  # ty: ignore[invalid-argument-type]
        allow_origins=cors_origins,
        allow_credentials=cors_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def bind_request_log_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid4())
        clear_contextvars()
        bind_contextvars(
            request_id=request_id,
            http_method=request.method,
            http_path=request.url.path,
        )
        trace_context = _get_active_trace_context()
        if trace_context:
            bind_contextvars(**trace_context)

        logger.info("API request started")
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("API request failed")
            raise
        else:
            logger.info("API request completed", status_code=response.status_code)
            return response
        finally:
            clear_contextvars()

    app.include_router(api_router)
    return app


app = create_app()


def main() -> None:
    """CLI entrypoint for running the API server."""
    uvicorn.run("finding_extractor.api:app", host="0.0.0.0", port=8001, reload=False)


if __name__ == "__main__":
    main()
