"""Async database engine and session lifecycle management.

The engine owns a connection pool and must be created once per process and
disposed on shutdown. Sessions are short-lived and scoped to a single request or
background job.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from truvix.shared.config import DatabaseSettings
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)


def create_engine(settings: DatabaseSettings) -> AsyncEngine:
    """Create the async engine and its connection pool.

    Args:
        settings: Database connection and pool configuration.

    Returns:
        A configured engine. The caller owns it and must dispose of it.
    """
    return create_async_engine(
        str(settings.dsn),
        echo=settings.echo_sql,
        pool_size=settings.pool_size,
        max_overflow=settings.max_overflow,
        pool_timeout=settings.pool_timeout_seconds,
        pool_recycle=settings.pool_recycle_seconds,
        # Verifies a pooled connection is alive before handing it out, which
        # prevents errors after a database restart or an idle-timeout kill.
        pool_pre_ping=True,
        connect_args={
            # Server-side ceiling so a pathological query cannot pin a
            # connection indefinitely and starve the pool.
            "server_settings": {
                "statement_timeout": str(settings.statement_timeout_seconds * 1000),
                "application_name": "truvix-backend",
            }
        },
    )


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create the session factory bound to the given engine.

    ``expire_on_commit`` is disabled so that ORM objects remain readable after
    the transaction commits, which lets a service return an entity that the
    response serialiser can still access.
    """
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


class Database:
    """Owns the engine and session factory for the lifetime of the process."""

    def __init__(self, settings: DatabaseSettings) -> None:
        """Initialise the engine and session factory.

        Args:
            settings: Database connection and pool configuration.
        """
        self._settings = settings
        self._engine = create_engine(settings)
        self._session_factory = create_session_factory(self._engine)

    @property
    def engine(self) -> AsyncEngine:
        """The underlying async engine."""
        return self._engine

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """The session factory bound to this engine."""
        return self._session_factory

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[AsyncSession]:
        """Yield a session wrapped in a transaction.

        Commits when the block exits normally and rolls back on any exception,
        so callers never have to remember which one to call.

        Yields:
            An open session participating in a single transaction.
        """
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def ping(self) -> bool:
        """Verify the database is reachable and accepting queries.

        Returns:
            ``True`` when a trivial query succeeds, ``False`` otherwise. Never
            raises, so a readiness probe can call it safely.
        """
        try:
            async with self._engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
        except SQLAlchemyError as exc:
            _logger.warning("database_ping_failed", error=str(exc))
            return False
        return True

    async def dispose(self) -> None:
        """Close every pooled connection. Call once during shutdown."""
        await self._engine.dispose()
        _logger.info("database_engine_disposed")
