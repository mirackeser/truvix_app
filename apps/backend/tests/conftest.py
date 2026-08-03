"""Shared pytest fixtures.

Tests run against a real PostgreSQL database and a real Redis instance rather
than fakes. Mocked infrastructure hides exactly the failures worth catching:
constraint violations, transaction semantics and dialect-specific behaviour.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.main import create_app
from truvix.shared.config import (
    DatabaseSettings,
    Environment,
    LogFormat,
    ObservabilitySettings,
    RedisSettings,
    SecuritySettings,
    Settings,
)
from truvix.shared.container import ApplicationContainer
from truvix.shared.database import Base

TEST_DATABASE_DSN = os.getenv(
    "TRUVIX_TEST_DB_DSN",
    "postgresql+asyncpg://truvix:truvix@localhost:5432/truvix_test",
)
TEST_REDIS_DSN = os.getenv("TRUVIX_TEST_REDIS_DSN", "redis://localhost:6379/15")

# Argon2 parameters are lowered to their configured minimum so that tests which
# hash passwords stay fast; production values are set through the environment.
_TEST_ARGON2_MEMORY_KIB = 8192
_TEST_ARGON2_TIME_COST = 1


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Configuration pointing at the disposable test infrastructure.

    ``_env_file=None`` throughout keeps a developer's local ``.env`` from
    leaking into the suite, so results do not depend on whose machine runs it.
    """
    return Settings(
        _env_file=None,
        environment=Environment.TESTING,
        trusted_hosts=["*"],
        cors_allowed_origins=[],
        database=DatabaseSettings(
            dsn=TEST_DATABASE_DSN, pool_size=5, max_overflow=5, _env_file=None
        ),
        redis=RedisSettings(dsn=TEST_REDIS_DSN, _env_file=None),
        security=SecuritySettings(
            secret_key="test-signing-key-that-is-long-enough-for-hs256",
            argon2_time_cost=_TEST_ARGON2_TIME_COST,
            argon2_memory_cost_kib=_TEST_ARGON2_MEMORY_KIB,
            _env_file=None,
        ),
        observability=ObservabilitySettings(
            log_level="WARNING", log_format=LogFormat.CONSOLE, _env_file=None
        ),
    )


@pytest.fixture(scope="session")
def anyio_backend() -> str:
    """Run async tests on asyncio only."""
    return "asyncio"


@pytest.fixture
async def container(settings: Settings) -> AsyncIterator[ApplicationContainer]:
    """A container wired to the test database, with a clean schema per test.

    The schema is dropped and recreated around every test so that no test can
    observe rows written by another, regardless of execution order.
    """
    instance = ApplicationContainer(settings)
    async with instance.database.engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    try:
        yield instance
    finally:
        await instance.redis.flushdb()
        await instance.aclose()


@pytest.fixture
async def session(container: ApplicationContainer) -> AsyncIterator[AsyncSession]:
    """A database session bound to the test container."""
    async with container.database.transaction() as active_session:
        yield active_session


@pytest.fixture
async def client(settings: Settings, container: ApplicationContainer) -> AsyncIterator[AsyncClient]:
    """An HTTP client bound to the application, bypassing the network stack.

    The application's own lifespan is not run; the test container is injected
    directly so that fixtures and request handlers share one database session
    factory and one Redis connection.
    """
    app = create_app(settings)
    app.state.container = container
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as http_client:
        yield http_client


@pytest.fixture(autouse=True)
def _reset_settings_cache() -> Iterator[None]:
    """Ensure a test that reads process settings cannot leak into the next one."""
    from truvix.shared.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
