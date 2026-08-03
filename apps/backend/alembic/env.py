"""Alembic migration environment.

The database URL comes from application settings rather than ``alembic.ini`` so
that credentials are configured in exactly one place and never committed. The
async engine is reused so migrations run against the same driver and connection
arguments as the application itself.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import Connection, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from truvix.models_registry import Base
from truvix.shared.config import get_settings

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_settings = get_settings()
config.set_main_option("sqlalchemy.url", str(_settings.database.dsn))


def _include_object(
    _object: object,
    name: str | None,
    type_: str,
    _reflected: bool,
    _compare_to: object,
) -> bool:
    """Exclude tables Alembic must not manage.

    Args:
        name: Name of the reflected or declared object.
        type_: The kind of object being considered, such as ``"table"``.

    Returns:
        ``False`` for objects that migrations should leave alone.
    """
    return not (type_ == "table" and name == "alembic_version")


def _configure(connection: Connection) -> None:
    """Apply the shared migration context configuration."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_object=_include_object,
        # Detect column type changes, which autogenerate ignores by default and
        # which would otherwise drift silently between the model and the schema.
        compare_type=True,
        compare_server_default=True,
        # Render the naming convention so constraint names in generated scripts
        # match the ones the database actually holds.
        render_as_batch=False,
    )


def run_migrations_offline() -> None:
    """Emit migration SQL without connecting to a database.

    Used to produce a reviewable script for a change-controlled deployment.
    """
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        include_object=_include_object,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _run_migrations(connection: Connection) -> None:
    """Run migrations on an established connection."""
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Apply migrations against the configured database."""
    engine = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_run_migrations)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
