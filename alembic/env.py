import os
from logging.config import fileConfig
from pathlib import Path

from sqlalchemy import engine_from_config
from sqlalchemy import pool
from sqlmodel import SQLModel

from alembic import context
from finding_extractor import store as _store  # noqa: F401
# Import store module for side effects so SQLModel table metadata is registered.

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)


def _resolve_sqlalchemy_url() -> str:
    """Resolve database URL for Alembic runtime.

    Priority:
    1) FINDING_EXTRACTOR_DB_URL (explicit SQLAlchemy URL)
    2) FINDING_EXTRACTOR_DB_PATH (project convention)
    3) alembic.ini sqlalchemy.url fallback
    """
    explicit_url = os.getenv("FINDING_EXTRACTOR_DB_URL")
    if explicit_url:
        return explicit_url

    db_path = os.getenv("FINDING_EXTRACTOR_DB_PATH")
    if db_path:
        resolved = Path(db_path).expanduser().resolve()
        return f"sqlite:///{resolved}"

    ini_url = config.get_main_option("sqlalchemy.url")
    if ini_url:
        return ini_url
    raise RuntimeError("No migration database URL configured")


config.set_main_option("sqlalchemy.url", _resolve_sqlalchemy_url())

# Alembic autogenerate target metadata.
target_metadata = SQLModel.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
