"""FastAPI app composition and health/readiness endpoints."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from finding_extractor.api_dependencies import get_store
from finding_extractor.api_models import HealthResponse
from finding_extractor.api_routes import router as api_router
from finding_extractor.config import get_settings
from finding_extractor.model_catalog import ModelCatalogService
from finding_extractor.store import ExtractionStore
from finding_extractor.tasks import register_run_extraction_task, run_extraction

logger = logging.getLogger(__name__)


async def assert_broker_ready(broker: Any) -> None:
    """Check broker backend connectivity for extraction dispatch readiness.

    Redis-backed brokers expose ``connection_pool``. Non-Redis test brokers
    (for example TaskIQ InMemoryBroker) are treated as locally ready.
    """

    connection_pool = getattr(broker, "connection_pool", None)
    if connection_pool is None:
        return

    from redis.asyncio import Redis

    async with Redis(connection_pool=connection_pool) as redis_conn:
        ping_result = redis_conn.ping()
        ping_ok = await ping_result if hasattr(ping_result, "__await__") else ping_result
        if ping_ok is not True:
            raise RuntimeError("Broker backend ping failed")


def create_app(store: ExtractionStore | None = None, broker: Any = None) -> FastAPI:
    """Create FastAPI app with injectable store/broker for tests."""
    settings = get_settings()
    uses_custom_broker = broker is not None
    if broker is None:
        from finding_extractor.broker import broker as default_broker

        broker = default_broker

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.store = store or ExtractionStore(settings.db_path)
        app.state.broker = broker
        app.state.model_catalog = ModelCatalogService(settings)
        app.state.run_extraction_task = (
            register_run_extraction_task(app.state.broker) if uses_custom_broker else run_extraction
        )
        await app.state.store.init()
        if not app.state.broker.is_worker_process:
            await app.state.broker.startup()
        try:
            yield
        finally:
            if not app.state.broker.is_worker_process:
                await app.state.broker.shutdown()
            await app.state.model_catalog.close()
            await app.state.store.close()

    app = FastAPI(title="Finding Extractor API", version="0.1.0", lifespan=lifespan)
    cors_origins = settings.cors_origins
    app.add_middleware(
        CORSMiddleware,  # ty: ignore[invalid-argument-type]
        allow_origins=cors_origins,
        allow_credentials=cors_origins != ["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/healthz", response_model=HealthResponse)
    async def healthz() -> HealthResponse:
        """Liveness probe for process-level health."""
        return HealthResponse(status="ok")

    @app.get("/api/readyz", response_model=HealthResponse)
    async def readyz(
        *,
        store: Annotated[ExtractionStore, Depends(get_store)],
        request: Request,
    ) -> HealthResponse:
        """Readiness probe for API/database and queue backend availability."""
        try:
            await store.list_reports(limit=1, offset=0)
            await assert_broker_ready(request.app.state.broker)
        except Exception as exc:
            logger.exception("Readiness check failed")
            raise HTTPException(status_code=503, detail="Not ready") from exc
        return HealthResponse(status="ready")

    app.include_router(api_router)
    return app


app = create_app()


def main() -> None:
    """CLI entrypoint for running the API server."""
    uvicorn.run("finding_extractor.api:app", host="0.0.0.0", port=8001, reload=False)


if __name__ == "__main__":
    main()
