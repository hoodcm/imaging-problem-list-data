"""Shared Pydantic base classes used across domain and API models."""

from pydantic import BaseModel, ConfigDict


class StrictBaseModel(BaseModel):
    """Project-wide strict model base (reject unknown fields)."""

    model_config = ConfigDict(extra="forbid")
