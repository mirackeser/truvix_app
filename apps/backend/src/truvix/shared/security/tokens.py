"""JWT issuing and verification for access and refresh tokens.

Access tokens are short-lived bearer credentials sent with every API call.
Refresh tokens are long-lived, single-use credentials that mint a new pair; each
carries a unique ``jti`` so the server can revoke an individual token and detect
replay of one that was already rotated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any, Final

import jwt
from jwt.exceptions import InvalidTokenError

from truvix.shared.config import SecuritySettings
from truvix.shared.errors import AuthenticationError

_ALGORITHM: Final = "HS256"
_ISSUER: Final = "truvix"
_AUDIENCE: Final = "truvix-api"


class TokenType(StrEnum):
    """Purpose a token was issued for."""

    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True)
class TokenClaims:
    """Verified claims extracted from a token."""

    subject: uuid.UUID
    token_id: uuid.UUID
    token_type: TokenType
    issued_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class IssuedToken:
    """A freshly minted token and the metadata needed to track it."""

    value: str
    token_id: uuid.UUID
    expires_at: datetime


class TokenService:
    """Issues and verifies signed JSON Web Tokens."""

    def __init__(self, settings: SecuritySettings) -> None:
        """Initialise the service.

        Args:
            settings: Security configuration supplying the signing key and TTLs.
        """
        self._signing_key = settings.signing_key
        self._access_ttl = timedelta(minutes=settings.access_token_ttl_minutes)
        self._refresh_ttl = timedelta(days=settings.refresh_token_ttl_days)

    @property
    def refresh_token_lifetime(self) -> timedelta:
        """How long an issued refresh token remains valid."""
        return self._refresh_ttl

    def issue_access_token(self, subject: uuid.UUID) -> IssuedToken:
        """Issue a short-lived access token for the given user.

        Args:
            subject: Identifier of the user the token authenticates.
        """
        return self._issue(subject, TokenType.ACCESS, self._access_ttl)

    def issue_refresh_token(self, subject: uuid.UUID) -> IssuedToken:
        """Issue a long-lived refresh token for the given user.

        Args:
            subject: Identifier of the user the token authenticates.
        """
        return self._issue(subject, TokenType.REFRESH, self._refresh_ttl)

    def decode(self, token: str, *, expected_type: TokenType) -> TokenClaims:
        """Verify a token's signature and claims.

        Args:
            token: The encoded JWT.
            expected_type: The purpose the token must have been issued for.

        Returns:
            The verified claims.

        Raises:
            AuthenticationError: If the token is malformed, expired, signed with
                the wrong key, or issued for a different purpose. The message is
                deliberately generic so it cannot be used as an oracle.
        """
        try:
            payload: dict[str, Any] = jwt.decode(
                token,
                self._signing_key,
                algorithms=[_ALGORITHM],
                issuer=_ISSUER,
                audience=_AUDIENCE,
                options={"require": ["exp", "iat", "sub", "jti", "typ"]},
            )
        except InvalidTokenError as exc:
            raise AuthenticationError("The provided token is invalid or has expired.") from exc

        if payload["typ"] != expected_type.value:
            raise AuthenticationError("The provided token is invalid or has expired.")

        try:
            return TokenClaims(
                subject=uuid.UUID(payload["sub"]),
                token_id=uuid.UUID(payload["jti"]),
                token_type=TokenType(payload["typ"]),
                issued_at=datetime.fromtimestamp(payload["iat"], tz=UTC),
                expires_at=datetime.fromtimestamp(payload["exp"], tz=UTC),
            )
        except (ValueError, KeyError, TypeError) as exc:
            raise AuthenticationError("The provided token is invalid or has expired.") from exc

    def _issue(self, subject: uuid.UUID, token_type: TokenType, ttl: timedelta) -> IssuedToken:
        """Mint and sign a token of the given type."""
        issued_at = datetime.now(UTC)
        expires_at = issued_at + ttl
        token_id = uuid.uuid7()

        payload = {
            "sub": str(subject),
            "jti": str(token_id),
            "typ": token_type.value,
            "iat": int(issued_at.timestamp()),
            "exp": int(expires_at.timestamp()),
            "iss": _ISSUER,
            "aud": _AUDIENCE,
        }
        encoded = jwt.encode(payload, self._signing_key, algorithm=_ALGORITHM)
        return IssuedToken(value=encoded, token_id=token_id, expires_at=expires_at)
