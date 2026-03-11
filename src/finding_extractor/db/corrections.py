"""Correction persistence helpers and public correction return type."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast
from uuid import uuid4

from sqlmodel import select

from finding_extractor.db.engine import StoreRuntime
from finding_extractor.db.extractions import get_finding_path
from finding_extractor.db.tables import CorrectionRow
from finding_extractor.models import CorrectionStatus, CorrectionType, Finding


@dataclass(frozen=True)
class StoredCorrection:
    """A persisted user correction against an extraction."""

    id: str
    extraction_id: str
    target_finding_index: int | None
    target_json_path: str | None
    correction_type: CorrectionType
    status: CorrectionStatus
    comment: str | None
    created_by: str | None
    username: str | None
    created_at: str


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _stored_correction_from_row(row: CorrectionRow) -> StoredCorrection:
    return StoredCorrection(
        id=row.id,
        extraction_id=row.extraction_id,
        target_finding_index=row.target_finding_index,
        target_json_path=row.target_json_path,
        correction_type=cast(CorrectionType, row.correction_type),
        status=cast(CorrectionStatus, row.status),
        comment=row.comment,
        created_by=row.created_by,
        username=row.username,
        created_at=row.created_at,
    )


async def record_correction(
    runtime: StoreRuntime,
    extraction_id: str,
    correction_type: CorrectionType,
    *,
    target_finding_index: int | None = None,
    target_json_path: str | None = None,
    proposed_finding: Finding | None = None,
    attribute_overrides: dict[str, str] | None = None,
    comment: str | None = None,
    created_by: str | None = None,
    username: str | None = None,
    status: CorrectionStatus = "pending",
) -> StoredCorrection:
    """Store user correction suggestions for later review/apply steps."""
    if correction_type == "add_finding" and proposed_finding is None:
        raise ValueError("add_finding corrections require proposed_finding")
    if correction_type == "update_finding" and (
        target_finding_index is None and target_json_path is None
    ):
        raise ValueError(
            "update_finding corrections require target_finding_index or target_json_path"
        )
    if correction_type == "comment" and not comment:
        raise ValueError("comment corrections require comment text")

    if target_json_path is None and target_finding_index is not None:
        target_json_path = await get_finding_path(runtime, extraction_id, target_finding_index)
        if correction_type == "update_finding" and target_json_path is None:
            raise ValueError(
                "update_finding target_finding_index does not exist in extraction findings"
            )

    correction_id = str(uuid4())
    created_at = _utc_now_iso()
    proposed_finding_json = (
        json.dumps(proposed_finding.model_dump(mode="json"), ensure_ascii=False)
        if proposed_finding is not None
        else None
    )
    attribute_overrides_json = (
        json.dumps(attribute_overrides, ensure_ascii=False) if attribute_overrides else None
    )

    async with runtime.session() as session:
        correction_row = CorrectionRow(
            id=correction_id,
            extraction_id=extraction_id,
            target_finding_index=target_finding_index,
            target_json_path=target_json_path,
            correction_type=correction_type,
            status=status,
            proposed_finding_json=proposed_finding_json,
            attribute_overrides_json=attribute_overrides_json,
            comment=comment,
            created_by=created_by,
            username=username,
            created_at=created_at,
        )
        session.add(correction_row)
        await session.commit()

    return _stored_correction_from_row(correction_row)


async def list_corrections(
    runtime: StoreRuntime, extraction_id: str
) -> list[StoredCorrection]:
    """List correction records for a given extraction."""
    async with runtime.session() as session:
        rows = (
            await session.exec(
                select(CorrectionRow)
                .where(CorrectionRow.extraction_id == extraction_id)
                .order_by(CorrectionRow.created_at, CorrectionRow.id)
            )
        ).all()

    return [_stored_correction_from_row(row) for row in rows]
