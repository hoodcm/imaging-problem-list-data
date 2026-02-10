"""FastAPI dependency helpers for API route modules."""

from fastapi import Request

from finding_extractor.store import ExtractionStore


def get_store(request: Request) -> ExtractionStore:
    """HTTP dependency for persistence access."""
    return request.app.state.store
