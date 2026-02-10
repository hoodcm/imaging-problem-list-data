"""FastAPI dependency helpers for API route modules."""

from fastapi import Request

from finding_extractor.model_catalog import ModelCatalogService
from finding_extractor.store import ExtractionStore


def get_store(request: Request) -> ExtractionStore:
    """HTTP dependency for persistence access."""
    return request.app.state.store


def get_model_catalog_service(request: Request) -> ModelCatalogService:
    """HTTP dependency for model discovery and cache access."""
    return request.app.state.model_catalog
