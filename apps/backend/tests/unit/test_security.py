"""Tests for password hashing and JWT issuing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt
import pytest

from truvix.shared.config import SecuritySettings
from truvix.shared.errors import AuthenticationError
from truvix.shared.security import PasswordHasherService, TokenService, TokenType

_TEST_ARGON2_MEMORY_KIB = 8192
_TEST_SIGNING_KEY = "unit-test-signing-key-long-enough-for-hs256"
_PASSWORD = "correct horse battery staple"


def _security_settings(**overrides: object) -> SecuritySettings:
    """Build security settings isolated from the developer's local ``.env``."""
    values: dict[str, object] = {
        "secret_key": _TEST_SIGNING_KEY,
        "argon2_time_cost": 1,
        "argon2_memory_cost_kib": _TEST_ARGON2_MEMORY_KIB,
    }
    values.update(overrides)
    return SecuritySettings(_env_file=None, **values)  # type: ignore[arg-type]


@pytest.fixture
def security_settings() -> SecuritySettings:
    """Security settings with cheap hashing parameters for fast tests."""
    return _security_settings()


@pytest.fixture
def hasher(security_settings: SecuritySettings) -> PasswordHasherService:
    """A password hasher bound to the test settings."""
    return PasswordHasherService(security_settings)


@pytest.fixture
def tokens(security_settings: SecuritySettings) -> TokenService:
    """A token service bound to the test settings."""
    return TokenService(security_settings)


class TestPasswordHashing:
    def test_hash_does_not_contain_the_plaintext(self, hasher: PasswordHasherService) -> None:
        digest = hasher.hash(_PASSWORD)

        assert _PASSWORD not in digest
        assert digest.startswith("$argon2id$")

    def test_correct_password_verifies(self, hasher: PasswordHasherService) -> None:
        assert hasher.verify(_PASSWORD, hasher.hash(_PASSWORD))

    def test_wrong_password_is_rejected(self, hasher: PasswordHasherService) -> None:
        assert not hasher.verify("wrong password", hasher.hash(_PASSWORD))

    def test_same_password_produces_distinct_hashes(self, hasher: PasswordHasherService) -> None:
        assert hasher.hash(_PASSWORD) != hasher.hash(_PASSWORD)

    def test_malformed_hash_is_treated_as_a_mismatch(self, hasher: PasswordHasherService) -> None:
        assert not hasher.verify(_PASSWORD, "not-a-valid-argon2-hash")

    def test_current_parameters_do_not_require_rehashing(
        self, hasher: PasswordHasherService
    ) -> None:
        assert not hasher.needs_rehash(hasher.hash(_PASSWORD))

    def test_weaker_parameters_require_rehashing(self) -> None:
        weaker = PasswordHasherService(
            _security_settings(argon2_memory_cost_kib=_TEST_ARGON2_MEMORY_KIB)
        )
        stronger = PasswordHasherService(
            _security_settings(argon2_memory_cost_kib=_TEST_ARGON2_MEMORY_KIB * 2)
        )

        assert stronger.needs_rehash(weaker.hash(_PASSWORD))

    def test_malformed_hash_requires_rehashing(self, hasher: PasswordHasherService) -> None:
        assert hasher.needs_rehash("not-a-valid-argon2-hash")


class TestTokenIssuing:
    def test_access_token_round_trips(self, tokens: TokenService) -> None:
        subject = uuid.uuid7()

        issued = tokens.issue_access_token(subject)
        claims = tokens.decode(issued.value, expected_type=TokenType.ACCESS)

        assert claims.subject == subject
        assert claims.token_type is TokenType.ACCESS
        assert claims.token_id == issued.token_id
        assert claims.expires_at > datetime.now(UTC)

    def test_refresh_token_round_trips(self, tokens: TokenService) -> None:
        subject = uuid.uuid7()

        issued = tokens.issue_refresh_token(subject)
        claims = tokens.decode(issued.value, expected_type=TokenType.REFRESH)

        assert claims.subject == subject
        assert claims.token_type is TokenType.REFRESH

    def test_each_token_gets_a_unique_identifier(self, tokens: TokenService) -> None:
        subject = uuid.uuid7()

        first = tokens.issue_access_token(subject)
        second = tokens.issue_access_token(subject)

        assert first.token_id != second.token_id

    def test_refresh_token_outlives_access_token(self, tokens: TokenService) -> None:
        subject = uuid.uuid7()

        access = tokens.issue_access_token(subject)
        refresh = tokens.issue_refresh_token(subject)

        assert refresh.expires_at > access.expires_at


class TestTokenVerification:
    def test_access_token_is_rejected_where_a_refresh_token_is_required(
        self, tokens: TokenService
    ) -> None:
        issued = tokens.issue_access_token(uuid.uuid7())

        with pytest.raises(AuthenticationError):
            tokens.decode(issued.value, expected_type=TokenType.REFRESH)

    def test_token_signed_with_another_key_is_rejected(self, tokens: TokenService) -> None:
        foreign = TokenService(_security_settings(secret_key="a-completely-different-key-value"))
        issued = foreign.issue_access_token(uuid.uuid7())

        with pytest.raises(AuthenticationError):
            tokens.decode(issued.value, expected_type=TokenType.ACCESS)

    def test_malformed_token_is_rejected(self, tokens: TokenService) -> None:
        with pytest.raises(AuthenticationError):
            tokens.decode("this.is.not-a-jwt", expected_type=TokenType.ACCESS)

    def test_expired_token_is_rejected(self, tokens: TokenService) -> None:
        expired = jwt.encode(
            {
                "sub": str(uuid.uuid7()),
                "jti": str(uuid.uuid7()),
                "typ": TokenType.ACCESS.value,
                "iat": 1_700_000_000,
                "exp": 1_700_000_060,
                "iss": "truvix",
                "aud": "truvix-api",
            },
            _TEST_SIGNING_KEY,
            algorithm="HS256",
        )

        with pytest.raises(AuthenticationError):
            tokens.decode(expired, expected_type=TokenType.ACCESS)

    def test_token_from_another_issuer_is_rejected(self, tokens: TokenService) -> None:
        foreign_issuer = jwt.encode(
            {
                "sub": str(uuid.uuid7()),
                "jti": str(uuid.uuid7()),
                "typ": TokenType.ACCESS.value,
                "iat": int(datetime.now(UTC).timestamp()),
                "exp": int(datetime.now(UTC).timestamp()) + 3600,
                "iss": "attacker",
                "aud": "truvix-api",
            },
            _TEST_SIGNING_KEY,
            algorithm="HS256",
        )

        with pytest.raises(AuthenticationError):
            tokens.decode(foreign_issuer, expected_type=TokenType.ACCESS)

    def test_unsigned_token_is_rejected(self, tokens: TokenService) -> None:
        unsigned = jwt.encode(
            {
                "sub": str(uuid.uuid7()),
                "jti": str(uuid.uuid7()),
                "typ": TokenType.ACCESS.value,
                "iat": int(datetime.now(UTC).timestamp()),
                "exp": int(datetime.now(UTC).timestamp()) + 3600,
                "iss": "truvix",
                "aud": "truvix-api",
            },
            key="",
            algorithm="none",
        )

        with pytest.raises(AuthenticationError):
            tokens.decode(unsigned, expected_type=TokenType.ACCESS)
