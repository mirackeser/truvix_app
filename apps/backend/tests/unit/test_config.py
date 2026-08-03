"""Tests for configuration loading and production hardening rules."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from truvix.shared.config import (
    DatabaseSettings,
    Environment,
    RedisSettings,
    SecuritySettings,
    Settings,
    generate_secret_key,
)

_VALID_DB_DSN = "postgresql+asyncpg://user:pass@localhost:5432/truvix"
_VALID_REDIS_DSN = "redis://localhost:6379/0"


def _settings(**overrides: object) -> Settings:
    """Build a Settings instance with valid infrastructure defaults.

    ``_env_file=None`` keeps the developer's local ``.env`` out of the test run;
    without it these assertions would pass or fail depending on whose machine
    they execute on.
    """
    base: dict[str, object] = {
        "database": DatabaseSettings(dsn=_VALID_DB_DSN, _env_file=None),
        "redis": RedisSettings(dsn=_VALID_REDIS_DSN, _env_file=None),
        "security": SecuritySettings(_env_file=None),
    }
    base.update(overrides)
    return Settings(_env_file=None, **base)  # type: ignore[arg-type]


class TestEnvironment:
    def test_staging_and_production_are_production_like(self) -> None:
        assert Environment.STAGING.is_production_like
        assert Environment.PRODUCTION.is_production_like

    def test_development_and_testing_are_not_production_like(self) -> None:
        assert not Environment.DEVELOPMENT.is_production_like
        assert not Environment.TESTING.is_production_like


class TestDocumentationExposure:
    def test_docs_are_available_outside_production(self) -> None:
        settings = _settings(environment=Environment.DEVELOPMENT)

        assert settings.docs_url == "/docs"
        assert settings.openapi_url == "/openapi.json"

    def test_docs_are_hidden_in_production(self) -> None:
        settings = _settings(
            environment=Environment.PRODUCTION,
            security=SecuritySettings(secret_key=generate_secret_key(), _env_file=None),
            trusted_hosts=["api.truvix.app"],
        )

        assert settings.docs_url is None
        assert settings.openapi_url is None


class TestProductionHardening:
    def test_default_secret_is_rejected_in_production(self) -> None:
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            _settings(environment=Environment.PRODUCTION, trusted_hosts=["api.truvix.app"])

    def test_short_secret_is_rejected_in_production(self) -> None:
        with pytest.raises(ValidationError, match="SECRET_KEY"):
            _settings(
                environment=Environment.PRODUCTION,
                security=SecuritySettings(secret_key="too-short", _env_file=None),
                trusted_hosts=["api.truvix.app"],
            )

    def test_wildcard_trusted_host_is_rejected_in_production(self) -> None:
        with pytest.raises(ValidationError, match="TRUSTED_HOSTS"):
            _settings(
                environment=Environment.PRODUCTION,
                security=SecuritySettings(secret_key=generate_secret_key(), _env_file=None),
                trusted_hosts=["*"],
            )

    def test_wildcard_cors_origin_is_rejected_in_production(self) -> None:
        with pytest.raises(ValidationError, match="CORS_ALLOWED_ORIGINS"):
            _settings(
                environment=Environment.PRODUCTION,
                security=SecuritySettings(secret_key=generate_secret_key(), _env_file=None),
                trusted_hosts=["api.truvix.app"],
                cors_allowed_origins=["*"],
            )

    def test_sql_echo_is_rejected_in_production(self) -> None:
        with pytest.raises(ValidationError, match="ECHO_SQL"):
            _settings(
                environment=Environment.PRODUCTION,
                security=SecuritySettings(secret_key=generate_secret_key(), _env_file=None),
                trusted_hosts=["api.truvix.app"],
                database=DatabaseSettings(dsn=_VALID_DB_DSN, echo_sql=True, _env_file=None),
            )

    def test_hardened_production_configuration_is_accepted(self) -> None:
        settings = _settings(
            environment=Environment.PRODUCTION,
            security=SecuritySettings(secret_key=generate_secret_key(), _env_file=None),
            trusted_hosts=["api.truvix.app"],
            cors_allowed_origins=["https://app.truvix.app"],
        )

        assert settings.environment is Environment.PRODUCTION
        assert not settings.debug

    def test_development_tolerates_relaxed_configuration(self) -> None:
        settings = _settings(environment=Environment.DEVELOPMENT)

        assert settings.debug
        assert settings.trusted_hosts == ["*"]


class TestDatabaseSettings:
    def test_sync_dsn_swaps_the_async_driver(self) -> None:
        database = DatabaseSettings(dsn=_VALID_DB_DSN, _env_file=None)

        assert database.sync_dsn.startswith("postgresql+psycopg://")
        assert "asyncpg" not in database.sync_dsn

    def test_pool_size_upper_bound_is_enforced(self) -> None:
        with pytest.raises(ValidationError):
            DatabaseSettings(dsn=_VALID_DB_DSN, pool_size=1000, _env_file=None)


class TestSecretGeneration:
    def test_generated_key_is_long_enough_for_production(self) -> None:
        assert len(generate_secret_key()) >= 32

    def test_generated_keys_are_unique(self) -> None:
        assert generate_secret_key() != generate_secret_key()
