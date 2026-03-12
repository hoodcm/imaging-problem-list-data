"""Mapping functions for API-shaped responses that are not store pass-through."""

from __future__ import annotations

import re

from finding_extractor.api.schemas import (
    AvailableModelResponse,
    CorrectionResponse,
    JobResponse,
    ModelCatalogResponse,
    StatusEventResponse,
    UserResponse,
)
from finding_extractor.db.store import (
    ExtractionStore,
    StoredCorrection,
    StoredJob,
    StoredUser,
)
from finding_extractor.llm.catalog import ModelCatalog


def _parse_status_event(message: str | None) -> StatusEventResponse | None:
    if message is None:
        return None
    trimmed = message.strip()
    if not trimmed:
        return None

    match = re.match(r"^\[stage:([a-z_]+)\]\s*(.*)$", trimmed, flags=re.IGNORECASE)
    if match is None:
        return None
    detail = match.group(2).strip() or None
    return StatusEventResponse(stage=match.group(1).lower(), detail=detail)


def map_job(job: StoredJob) -> JobResponse:
    status_event = _parse_status_event(job.status_message)
    return JobResponse(
        job_id=job.id,
        report_id=job.report_id,
        status=job.status,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
        extraction_id=job.extraction_id,
        error=job.error,
        status_message=job.status_message,
        status_event=status_event,
        warning_payload=job.warning_payload,
    )


def _user_response(user: StoredUser) -> UserResponse:
    return UserResponse(
        username=user.username,
        name=user.name,
        email=user.email,
    )


async def map_correction(
    correction: StoredCorrection, store: ExtractionStore
) -> CorrectionResponse:
    """Map correction with author lookup."""
    author = None
    if correction.username:
        user = await store.get_user(correction.username)
        if user:
            author = _user_response(user)

    return CorrectionResponse(
        id=correction.id,
        extraction_id=correction.extraction_id,
        target_finding_index=correction.target_finding_index,
        target_json_path=correction.target_json_path,
        correction_type=correction.correction_type,
        status=correction.status,
        comment=correction.comment,
        author=author,
        created_by=correction.created_by,
        created_at=correction.created_at,
    )


def map_correction_with_users(
    correction: StoredCorrection, user_map: dict[str, StoredUser]
) -> CorrectionResponse:
    """Map correction with pre-fetched user map (avoids N+1 queries)."""
    author = None
    if correction.username and correction.username in user_map:
        author = _user_response(user_map[correction.username])

    return CorrectionResponse(
        id=correction.id,
        extraction_id=correction.extraction_id,
        target_finding_index=correction.target_finding_index,
        target_json_path=correction.target_json_path,
        correction_type=correction.correction_type,
        status=correction.status,
        comment=correction.comment,
        author=author,
        created_by=correction.created_by,
        created_at=correction.created_at,
    )


def map_user(user: StoredUser) -> UserResponse:
    return _user_response(user)


def map_model_catalog(catalog: ModelCatalog) -> ModelCatalogResponse:
    return ModelCatalogResponse(
        updated_at=catalog.updated_at,
        stale=catalog.stale,
        refresh_interval_seconds=catalog.refresh_interval_seconds,
        models=[
            AvailableModelResponse(
                id=model.id,
                provider=model.provider,
                tier=model.tier,
                is_default=model.is_default,
                supported_reasoning=model.supported_reasoning,
                default_reasoning=model.default_reasoning,
            )
            for model in catalog.models
        ],
    )
