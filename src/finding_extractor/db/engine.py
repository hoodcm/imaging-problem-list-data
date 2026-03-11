"""Engine and session management for SQLite persistence."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession


class StoreRuntime:
    """Own the async engine, session factory, and migration preflight helpers."""

    EXPECTED_REVISION = "3d867b54ee78"

    def __init__(self, db_path: Path | str):
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._engine: AsyncEngine = create_async_engine(
            f"sqlite+aiosqlite:///{self._db_path}",
            echo=False,
        )
        self._configure_sqlite_pragmas()
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        self._initialized = False

    def _configure_sqlite_pragmas(self) -> None:
        """Apply SQLite pragmas that make API + worker access reliable."""

        @event.listens_for(self._engine.sync_engine, "connect")
        def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
            _ = connection_record
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    @property
    def db_path(self) -> Path:
        """Configured SQLite path."""
        return self._db_path

    @property
    def engine(self) -> AsyncEngine:
        """Expose async engine for tests/integration wiring."""
        return self._engine

    async def init(self) -> None:
        """Initialize database tables (idempotent)."""
        if self._initialized:
            return
        async with self._engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        self._initialized = True

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Provide an AsyncSession context manager."""
        await self.init()
        async with self._session_factory() as session:
            yield session

    async def check_migration_current(self) -> str | None:
        """Check DB is at the expected Alembic migration revision."""
        async with self._engine.connect() as conn:
            try:
                row = (await conn.execute(text("SELECT version_num FROM alembic_version"))).first()
            except OperationalError:
                return (
                    "Database has no alembic_version table (never migrated). "
                    "Run 'task db:migrate' to initialize."
                )
            if row is None:
                return (
                    "Database alembic_version table is empty (no revision stamped). "
                    "Run 'task db:migrate' to apply migrations."
                )
            current = row[0]
            if current != self.EXPECTED_REVISION:
                return (
                    f"Database is at revision {current}, "
                    f"expected {self.EXPECTED_REVISION}. "
                    "Run 'task db:migrate' to upgrade."
                )
        return None

    async def close(self) -> None:
        """Dispose async engine and pooled connections."""
        await self._engine.dispose()
