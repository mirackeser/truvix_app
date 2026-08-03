"""Application configuration loaded from the environment.

Every tunable value in the platform is declared here so that no module reaches
for ``os.environ`` directly. Settings are validated once at import time, which
turns a misconfigured deployment into an immediate, descriptive startup failure
rather than an obscure runtime error hours later.
"""

from __future__ import annotations

import secrets
from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Self

from pydantic import Field, PostgresDsn, RedisDsn, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_MIN_SECRET_LENGTH = 32
_DEVELOPMENT_SECRET_SENTINEL = "change-me"  # noqa: S105 - sentinel that production config rejects

# Each settings group is constructed independently, so every one of them must be
# told where the local override file lives; a parent's env_file is not inherited.
_ENV_FILE = ".env"


def _group_config(env_prefix: str) -> SettingsConfigDict:
    """Build the shared configuration for a settings group.

    Args:
        env_prefix: Environment variable prefix scoping the group's fields.
    """
    return SettingsConfigDict(
        env_prefix=env_prefix,
        env_file=_ENV_FILE,
        env_file_encoding="utf-8",
        extra="ignore",
    )


class Environment(StrEnum):
    """Deployment environment the process is running in."""

    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"

    @property
    def is_production_like(self) -> bool:
        """Whether hardening rules that must never be relaxed apply."""
        return self in {Environment.STAGING, Environment.PRODUCTION}


class LogFormat(StrEnum):
    """Rendering style for emitted log records."""

    JSON = "json"
    CONSOLE = "console"


class DatabaseSettings(BaseSettings):
    """PostgreSQL connection and pool configuration."""

    model_config = _group_config("TRUVIX_DB_")

    dsn: PostgresDsn = Field(
        description="Async PostgreSQL DSN, e.g. postgresql+asyncpg://user:pass@host:5432/truvix",
    )
    pool_size: Annotated[int, Field(ge=1, le=100)] = 10
    max_overflow: Annotated[int, Field(ge=0, le=100)] = 20
    pool_timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 30.0
    pool_recycle_seconds: Annotated[int, Field(gt=0)] = 1800
    echo_sql: bool = False
    statement_timeout_seconds: Annotated[int, Field(gt=0, le=300)] = 30

    @property
    def sync_dsn(self) -> str:
        """Synchronous DSN, required by Alembic's migration runner."""
        return str(self.dsn).replace("+asyncpg", "+psycopg", 1)


class RedisSettings(BaseSettings):
    """Redis connection configuration for caching and rate limiting."""

    model_config = _group_config("TRUVIX_REDIS_")

    dsn: RedisDsn = Field(description="Redis DSN, e.g. redis://localhost:6379/0")
    max_connections: Annotated[int, Field(ge=1, le=500)] = 50
    socket_timeout_seconds: Annotated[float, Field(gt=0, le=30)] = 5.0


class SecuritySettings(BaseSettings):
    """Token signing, password hashing and rate limiting parameters."""

    model_config = _group_config("TRUVIX_SECURITY_")

    secret_key: SecretStr = Field(
        default_factory=lambda: SecretStr(_DEVELOPMENT_SECRET_SENTINEL),
        description="HMAC signing key for JWTs. Must be overridden outside development.",
    )
    access_token_ttl_minutes: Annotated[int, Field(ge=1, le=1440)] = 30
    refresh_token_ttl_days: Annotated[int, Field(ge=1, le=365)] = 30

    argon2_time_cost: Annotated[int, Field(ge=1, le=10)] = 3
    argon2_memory_cost_kib: Annotated[int, Field(ge=8192, le=1_048_576)] = 65536
    argon2_parallelism: Annotated[int, Field(ge=1, le=16)] = 4

    max_failed_login_attempts: Annotated[int, Field(ge=3, le=20)] = 5
    account_lockout_minutes: Annotated[int, Field(ge=1, le=1440)] = 15

    @property
    def signing_key(self) -> str:
        """The raw signing key, unwrapped from its secret container."""
        return self.secret_key.get_secret_value()


class RateLimitSettings(BaseSettings):
    """Global request throttling thresholds."""

    model_config = _group_config("TRUVIX_RATELIMIT_")

    enabled: bool = True
    authenticated_requests_per_minute: Annotated[int, Field(ge=1, le=10_000)] = 120
    anonymous_requests_per_minute: Annotated[int, Field(ge=1, le=10_000)] = 30
    auth_endpoint_requests_per_minute: Annotated[int, Field(ge=1, le=1_000)] = 10


class StorageSettings(BaseSettings):
    """Uploaded-file storage configuration."""

    model_config = _group_config("TRUVIX_STORAGE_")

    root_dir: Path = Field(
        default=Path("storage"),
        description="Directory that holds every uploaded object.",
    )
    max_upload_bytes: Annotated[int, Field(ge=1024, le=100 * 1024 * 1024)] = 15 * 1024 * 1024
    max_photos_per_analysis: Annotated[int, Field(ge=1, le=50)] = 12


class ObservabilitySettings(BaseSettings):
    """Logging and telemetry configuration."""

    model_config = _group_config("TRUVIX_OBS_")

    log_level: str = Field(default="INFO", pattern="^(DEBUG|INFO|WARNING|ERROR|CRITICAL)$")
    log_format: LogFormat = LogFormat.JSON
    sentry_dsn: SecretStr | None = None
    slow_request_threshold_ms: Annotated[int, Field(ge=1)] = 1000


class Settings(BaseSettings):
    """Root configuration object composing every settings group."""

    model_config = _group_config("TRUVIX_")

    environment: Environment = Environment.DEVELOPMENT
    app_name: str = "Truvix API"
    api_v1_prefix: str = "/api/v1"

    cors_allowed_origins: list[str] = Field(default_factory=list)
    trusted_hosts: list[str] = Field(default_factory=lambda: ["*"])

    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    security: SecuritySettings = Field(default_factory=SecuritySettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    storage: StorageSettings = Field(default_factory=StorageSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)

    @property
    def debug(self) -> bool:
        """Whether developer-facing diagnostics may be exposed."""
        return self.environment is Environment.DEVELOPMENT

    @property
    def docs_url(self) -> str | None:
        """OpenAPI docs path, disabled in production-like environments."""
        return None if self.environment.is_production_like else "/docs"

    @property
    def openapi_url(self) -> str | None:
        """OpenAPI schema path, disabled in production-like environments."""
        return None if self.environment.is_production_like else "/openapi.json"

    @model_validator(mode="after")
    def _enforce_production_hardening(self) -> Self:
        """Reject configurations that are unsafe for a production-like deployment."""
        if not self.environment.is_production_like:
            return self

        key = self.security.signing_key
        if key == _DEVELOPMENT_SECRET_SENTINEL or len(key) < _MIN_SECRET_LENGTH:
            raise ValueError(
                "TRUVIX_SECURITY_SECRET_KEY must be an explicit value of at least "
                f"{_MIN_SECRET_LENGTH} characters in {self.environment} environments"
            )
        if "*" in self.trusted_hosts:
            raise ValueError(
                "TRUVIX_TRUSTED_HOSTS must list explicit hostnames in "
                f"{self.environment} environments"
            )
        if "*" in self.cors_allowed_origins:
            raise ValueError(
                "TRUVIX_CORS_ALLOWED_ORIGINS must list explicit origins in "
                f"{self.environment} environments"
            )
        if self.database.echo_sql:
            raise ValueError(
                "TRUVIX_DB_ECHO_SQL must be disabled in "
                f"{self.environment} environments to avoid leaking data into logs"
            )
        return self


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings instance.

    Cached so that environment parsing and validation happen exactly once. Tests
    that need to alter configuration should call ``get_settings.cache_clear()``.
    """
    return Settings()


def generate_secret_key() -> str:
    """Generate a cryptographically secure signing key for a new deployment."""
    return secrets.token_urlsafe(_MIN_SECRET_LENGTH)
