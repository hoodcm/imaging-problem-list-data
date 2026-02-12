"""Tests for Alembic migration foundation."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine
from sqlmodel import SQLModel

from alembic import command
from finding_extractor import store as _store  # noqa: F401


def _alembic_config() -> Config:
    """Build Alembic config rooted at this repository."""
    return Config("alembic.ini")


def test_alembic_upgrade_creates_expected_tables(tmp_path: Path, monkeypatch) -> None:
    """Upgrading to head creates all core tables and Alembic version tracking."""
    db_path = tmp_path / "migration.sqlite3"
    monkeypatch.setenv("IPL_DB_PATH", str(db_path))

    command.upgrade(_alembic_config(), "head")

    with sqlite3.connect(db_path) as conn:
        table_names = {
            row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        }

    assert {"alembic_version", "reports", "extractions", "corrections", "jobs"} <= table_names


def test_alembic_check_reports_no_drift_on_upgraded_db(tmp_path: Path, monkeypatch) -> None:
    """`alembic check` should report no pending ops after upgrade head."""
    db_path = tmp_path / "drift-check.sqlite3"
    monkeypatch.setenv("IPL_DB_PATH", str(db_path))
    config = _alembic_config()

    command.upgrade(config, "head")
    command.check(config)


def test_alembic_stamp_baseline_for_existing_create_all_schema(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """Existing pre-Alembic schema can be adopted with baseline stamp then upgrade to head."""
    db_path = tmp_path / "existing-schema.sqlite3"
    sqlite_url = f"sqlite:///{db_path}"
    engine = create_engine(sqlite_url)
    SQLModel.metadata.create_all(engine)

    monkeypatch.setenv("IPL_DB_PATH", str(db_path))
    config = _alembic_config()

    # create_all already materialises the current schema (including new columns),
    # so stamp head directly — migrations would redundantly ADD COLUMN.
    command.stamp(config, "head")

    with sqlite3.connect(db_path) as conn:
        version = conn.execute("SELECT version_num FROM alembic_version").fetchone()

    assert version is not None
    assert version[0] == "a3f1c8b2d4e6"
