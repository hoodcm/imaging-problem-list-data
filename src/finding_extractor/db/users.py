"""User persistence helpers and public user return type."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlmodel import select

from finding_extractor.db.engine import StoreRuntime
from finding_extractor.db.tables import UserRow


@dataclass(frozen=True)
class StoredUser:
    """A persisted user account."""

    username: str
    name: str
    email: str
    created_at: str


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _stored_user_from_row(row: UserRow) -> StoredUser:
    return StoredUser(
        username=row.username,
        name=row.name,
        email=row.email,
        created_at=row.created_at,
    )


async def create_user(
    runtime: StoreRuntime, username: str, name: str, email: str
) -> StoredUser:
    """Create a new user account (upsert semantics: updates if username exists)."""
    async with runtime.session() as session:
        existing = (await session.exec(select(UserRow).where(UserRow.username == username))).first()

        if existing is not None:
            existing.name = name
            existing.email = email
            session.add(existing)
            await session.commit()
            await session.refresh(existing)
            return _stored_user_from_row(existing)

        user_row = UserRow(
            username=username,
            name=name,
            email=email,
            created_at=_utc_now_iso(),
        )
        session.add(user_row)
        await session.commit()

        return _stored_user_from_row(user_row)


async def get_user(runtime: StoreRuntime, username: str) -> StoredUser | None:
    """Get a user by username."""
    async with runtime.session() as session:
        row = (await session.exec(select(UserRow).where(UserRow.username == username))).first()
        return _stored_user_from_row(row) if row else None


async def list_users(runtime: StoreRuntime) -> list[StoredUser]:
    """List all users, ordered by username."""
    async with runtime.session() as session:
        rows = (await session.exec(select(UserRow).order_by(UserRow.username))).all()

    return [_stored_user_from_row(row) for row in rows]
