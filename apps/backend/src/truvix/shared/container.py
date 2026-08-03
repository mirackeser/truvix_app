"""Composition root wiring long-lived infrastructure dependencies.

Constructing every shared resource in one place keeps the application free of
module-level singletons: tests build a container against a throwaway database
and inject it, instead of monkey-patching global state.
"""

from __future__ import annotations

from types import TracebackType
from typing import Self

from redis.asyncio import ConnectionPool, Redis
from redis.exceptions import RedisError

from truvix.shared.config import Settings
from truvix.shared.database import Database
from truvix.shared.logging import get_logger
from truvix.shared.security import PasswordHasherService, TokenService
from truvix.shared.storage import LocalFileStorage

_logger = get_logger(__name__)


class ApplicationContainer:
    """Owns every process-scoped dependency and their shutdown order."""

    def __init__(self, settings: Settings) -> None:
        """Construct the container's resources.

        Args:
            settings: Fully validated application configuration.
        """
        self._settings = settings
        self._database = Database(settings.database)
        self._redis_pool = ConnectionPool.from_url(
            str(settings.redis.dsn),
            max_connections=settings.redis.max_connections,
            socket_timeout=settings.redis.socket_timeout_seconds,
            socket_connect_timeout=settings.redis.socket_timeout_seconds,
            decode_responses=True,
        )
        self._redis: Redis = Redis(connection_pool=self._redis_pool)
        self._password_hasher = PasswordHasherService(settings.security)
        self._token_service = TokenService(settings.security)
        self._file_storage = LocalFileStorage(settings.storage.root_dir)

    @property
    def settings(self) -> Settings:
        """The configuration this container was built from."""
        return self._settings

    @property
    def database(self) -> Database:
        """The database engine and session factory."""
        return self._database

    @property
    def redis(self) -> Redis:
        """The shared Redis client."""
        return self._redis

    @property
    def password_hasher(self) -> PasswordHasherService:
        """The Argon2 password hashing service."""
        return self._password_hasher

    @property
    def token_service(self) -> TokenService:
        """The JWT issuing and verification service."""
        return self._token_service

    @property
    def file_storage(self) -> LocalFileStorage:
        """The uploaded-file store."""
        return self._file_storage

    async def ping_redis(self) -> bool:
        """Verify Redis is reachable.

        Returns:
            ``True`` when Redis responds, ``False`` otherwise. Never raises, so
            a readiness probe can call it safely.
        """
        try:
            await self._redis.ping()
        except RedisError as exc:
            _logger.warning("redis_ping_failed", error=str(exc))
            return False
        return True

    async def aclose(self) -> None:
        """Release every held resource. Safe to call once during shutdown."""
        await self._redis.aclose()
        await self._redis_pool.disconnect()
        await self._database.dispose()
        _logger.info("application_container_closed")

    async def __aenter__(self) -> Self:
        """Enter the container's lifetime scope."""
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the container when leaving its lifetime scope."""
        await self.aclose()
