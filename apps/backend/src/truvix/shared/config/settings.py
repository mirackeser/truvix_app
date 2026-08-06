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

from pydantic import Field, HttpUrl, PostgresDsn, RedisDsn, SecretStr, model_validator
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
    store_notification_requests_per_minute: Annotated[int, Field(ge=1, le=10_000)] = 300
    """Ceiling for the App Store notification webhook.

    Set generously because Apple batches renewals and the endpoint is the only
    way a refund reaches us. It exists because the route is unauthenticated and
    parses certificates, so an open flood would otherwise cost real work.
    """


class StorageSettings(BaseSettings):
    """Uploaded-file storage configuration."""

    model_config = _group_config("TRUVIX_STORAGE_")

    root_dir: Path = Field(
        default=Path("storage"),
        description="Directory that holds every uploaded object.",
    )
    max_upload_bytes: Annotated[int, Field(ge=1024, le=100 * 1024 * 1024)] = 15 * 1024 * 1024
    max_photos_per_analysis: Annotated[int, Field(ge=1, le=50)] = 12


class SubscriptionSettings(BaseSettings):
    """App Store subscription verification configuration.

    Without ``bundle_id`` the endpoints refuse every transaction rather than
    accepting any: a verifier that does not know which application it serves
    would accept a genuine Apple signature issued for somebody else's app.
    """

    model_config = _group_config("TRUVIX_SUBSCRIPTION_")

    bundle_id: str | None = Field(
        default=None,
        description="The iOS bundle identifier a transaction must name.",
    )
    apple_root_certificate_dir: Path = Field(
        default=Path("certs/apple"),
        description=(
            "Directory holding Apple's root certificates. They are shipped "
            "rather than fetched: a root downloaded at runtime is a root an "
            "attacker on the network could substitute."
        ),
    )
    allow_sandbox: bool = Field(
        default=False,
        description=(
            "Whether Apple's sandbox transactions are honoured. Off by default "
            "and rejected outright in production: a sandbox purchase costs "
            "nothing yet carries a genuine Apple signature, so honouring one "
            "would hand premium to anybody with a free test account. Developers "
            "testing against the sandbox turn it on deliberately."
        ),
    )

    @property
    def enabled(self) -> bool:
        """Whether purchases can be verified at all."""
        return self.bundle_id is not None


class EmailSettings(BaseSettings):
    """Outbound mail configuration.

    SMTP rather than a vendor SDK: every provider speaks it, so switching from
    one to another is a configuration change. With no host configured the
    application logs messages instead of sending them, which keeps development
    working without a mail server and makes the link visible in the log.
    """

    model_config = _group_config("TRUVIX_EMAIL_")

    host: str | None = Field(default=None, description="SMTP host. Unset disables sending.")
    port: Annotated[int, Field(ge=1, le=65535)] = 587
    username: str | None = None
    password: SecretStr | None = None
    #: Implicit TLS, the whole session encrypted from the first byte (port 465).
    use_tls: bool = False
    #: Explicit TLS, upgrading a plain connection (port 587). The usual choice.
    use_starttls: bool = True
    from_address: str = Field(
        default="Truvix <noreply@truvix.app>",
        description="The From header on every message.",
    )
    timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 15.0
    verification_ttl_hours: Annotated[int, Field(ge=1, le=168)] = 24
    password_reset_ttl_hours: Annotated[int, Field(ge=1, le=24)] = 2
    """How long a reset link lasts.

    Shorter than a verification link, and capped lower. A verification link that
    sits unused in an inbox grants nothing; a reset link grants the account.
    """
    password_reset_base_url: HttpUrl = Field(
        default=HttpUrl("https://truvix.app/reset-password.html"),
        description=(
            "Where a reset link points. A web page that reads the token from "
            "its query string and posts it, with the new password, to "
            "/auth/password/reset."
        ),
    )
    verification_base_url: HttpUrl = Field(
        default=HttpUrl("https://truvix.app/verify-email"),
        description=(
            "Where a verification link points. This must be a web page that "
            "reads the token from its query string and POSTs it to "
            "/auth/email/verify — the app does not claim the domain, so the "
            "link opens a browser rather than the app."
        ),
    )

    @property
    def configured(self) -> bool:
        """Whether mail can actually be delivered."""
        return self.host is not None


class ApnsSettings(BaseSettings):
    """Apple Push Notification service credentials.

    Token-based rather than certificate-based: a p8 signing key does not expire,
    where a push certificate does and takes notifications down on a day nobody
    is watching. With no key configured the application logs what it would have
    sent, so development needs no Apple account.
    """

    model_config = _group_config("TRUVIX_APNS_")

    key_id: str | None = Field(default=None, description="The p8 key's identifier, from Apple.")
    team_id: str | None = Field(default=None, description="The Apple Developer team id.")
    private_key: SecretStr | None = Field(
        default=None,
        description=(
            "The p8 signing key, PEM encoded. Supplied whole, newlines and all; "
            "a key mangled into one line will not parse."
        ),
    )
    bundle_id: str | None = Field(
        default=None, description="The app's bundle id, sent as the APNs topic."
    )
    use_sandbox: bool = Field(
        default=True,
        description=(
            "Whether to send to Apple's sandbox. Development builds register "
            "sandbox tokens, which the production host rejects outright, so "
            "this must match how the app was built."
        ),
    )

    @property
    def configured(self) -> bool:
        """Whether notifications can actually be sent."""
        return all((self.key_id, self.team_id, self.private_key, self.bundle_id))

    @property
    def signing_key(self) -> str:
        """The raw signing key, unwrapped from its secret container."""
        return self.private_key.get_secret_value() if self.private_key else ""


class QuotaSettings(BaseSettings):
    """Per-account ceilings on what one user may consume.

    Every analysis costs real money — a vision call over several images and a
    reasoning call — and every upload costs storage. Without a ceiling one
    authenticated account can spend the platform's entire AI budget and fill
    its disk, which needs no exploit at all, only a loop.

    The ceilings also give the subscription tier something to mean.
    """

    model_config = _group_config("TRUVIX_QUOTA_")

    free_analyses_per_day: Annotated[int, Field(ge=1, le=1000)] = 5
    premium_analyses_per_day: Annotated[int, Field(ge=1, le=10_000)] = 100

    free_vehicles: Annotated[int, Field(ge=1, le=10_000)] = 20
    premium_vehicles: Annotated[int, Field(ge=1, le=100_000)] = 500


class AISettings(BaseSettings):
    """AI provider configuration.

    Leaving ``api_key`` unset disables AI features cleanly: analyses fall back
    to the rule-based engine and the copilot reports itself unavailable, rather
    than the application failing to start.
    """

    model_config = _group_config("TRUVIX_AI_")

    api_key: SecretStr | None = Field(
        default=None,
        description="OpenAI API key. Absent means AI features are disabled.",
    )
    base_url: HttpUrl = Field(default=HttpUrl("https://api.openai.com/v1"))
    model: str = "gpt-4o-mini"
    temperature: Annotated[float, Field(ge=0, le=2)] = 0.3
    max_output_tokens: Annotated[int, Field(ge=64, le=16_384)] = 1024
    request_timeout_seconds: Annotated[float, Field(gt=0, le=120)] = 30.0
    copilot_messages_per_minute: Annotated[int, Field(ge=1, le=100)] = 10
    copilot_history_window: Annotated[int, Field(ge=2, le=50)] = 12

    @property
    def enabled(self) -> bool:
        """Whether a provider is configured."""
        return self.api_key is not None


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
    email: EmailSettings = Field(default_factory=EmailSettings)
    apns: ApnsSettings = Field(default_factory=ApnsSettings)
    quota: QuotaSettings = Field(default_factory=QuotaSettings)
    subscription: SubscriptionSettings = Field(default_factory=SubscriptionSettings)
    ai: AISettings = Field(default_factory=AISettings)
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
        if self.subscription.allow_sandbox and self.environment is Environment.PRODUCTION:
            raise ValueError(
                "TRUVIX_SUBSCRIPTION_ALLOW_SANDBOX must be false in production; "
                "sandbox purchases are free and would grant premium to anyone"
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
