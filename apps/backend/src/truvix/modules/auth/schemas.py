"""Request and response models for the authentication endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from truvix.modules.users.models import (
    FULL_NAME_MAX_LENGTH,
    SubscriptionTier,
    User,
)
from truvix.shared.schemas import StrictRequest

# NIST SP 800-63B advises length over composition rules: long passphrases beat
# short passwords padded with symbols, and composition rules push users toward
# predictable substitutions.
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128

FULL_NAME_MIN_LENGTH = 2

# Below this length an email's local part is too generic to treat as a secret
# fragment; checking it would reject ordinary passwords for no benefit.
MIN_EMAIL_LOCAL_PART_FOR_REUSE_CHECK = 4

_E164_PATTERN = r"^\+[1-9]\d{7,14}$"

PasswordStr = Annotated[str, Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)]
PhoneNumberStr = Annotated[str, Field(pattern=_E164_PATTERN)]


class RegistrationRequest(StrictRequest):
    """Payload for creating a new account."""

    email: EmailStr
    password: PasswordStr
    full_name: Annotated[
        str, Field(min_length=FULL_NAME_MIN_LENGTH, max_length=FULL_NAME_MAX_LENGTH)
    ]
    phone_number: PhoneNumberStr | None = None

    @field_validator("password")
    @classmethod
    def _reject_whitespace_only_password(cls, value: str) -> str:
        """Reject passwords that carry no actual entropy."""
        if not value.strip():
            raise ValueError("Password must contain non-whitespace characters.")
        return value

    @model_validator(mode="after")
    def _reject_password_containing_email(self) -> Self:
        """Reject passwords built from the account's own address.

        Very short local parts are skipped: someone whose address is ``a@x.com``
        would otherwise be unable to choose any password containing the letter
        "a", which is a usability failure rather than a security gain.
        """
        local_part = self.email.split("@", 1)[0].lower()
        if len(local_part) < MIN_EMAIL_LOCAL_PART_FOR_REUSE_CHECK:
            return self
        if local_part in self.password.lower():
            raise ValueError("Password must not contain your email address.")
        return self


class LoginRequest(StrictRequest):
    """Payload for exchanging credentials for a token pair."""

    email: EmailStr
    password: Annotated[str, Field(min_length=1, max_length=PASSWORD_MAX_LENGTH)]


class RefreshRequest(StrictRequest):
    """Payload for exchanging a refresh token for a new pair."""

    refresh_token: Annotated[str, Field(min_length=1)]


class DeleteAccountRequest(StrictRequest):
    """Confirmation that the account holder means it."""

    password: Annotated[str, Field(min_length=1, max_length=512)]


class RequestPasswordResetRequest(StrictRequest):
    """The address somebody typed into the "forgot password" form."""

    email: EmailStr


class ResetPasswordRequest(StrictRequest):
    """A reset link and the password to put behind it."""

    token: Annotated[str, Field(min_length=16, max_length=256)]
    password: PasswordStr

    @field_validator("password")
    @classmethod
    def _reject_whitespace_only_password(cls, value: str) -> str:
        """Reject passwords that carry no actual entropy."""
        if not value.strip():
            raise ValueError("Password must contain non-whitespace characters.")
        return value


class VerifyEmailRequest(StrictRequest):
    """The token carried by a verification link."""

    token: Annotated[str, Field(min_length=16, max_length=256)]


class LogoutRequest(StrictRequest):
    """Payload for ending a single session."""

    refresh_token: Annotated[str, Field(min_length=1)]


class TokenPairResponse(BaseModel):
    """A freshly issued access and refresh token pair."""

    access_token: str
    refresh_token: str
    token_type: Annotated[str, Field(description="Always 'bearer'.")] = "bearer"  # noqa: S105
    expires_in: Annotated[int, Field(description="Access token lifetime in seconds.")]


class UserResponse(BaseModel):
    """Public view of an account."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: EmailStr
    full_name: str
    phone_number: str | None
    subscription_tier: SubscriptionTier
    email_verified: bool
    created_at: datetime

    @classmethod
    def from_user(cls, user: User) -> Self:
        """Build the response from a persisted account.

        Args:
            user: The account to expose.
        """
        return cls(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            phone_number=user.phone_number,
            subscription_tier=user.subscription_tier,
            email_verified=user.is_email_verified,
            created_at=user.created_at,
        )


class AuthenticatedResponse(BaseModel):
    """The account together with the tokens issued for it."""

    user: UserResponse
    tokens: TokenPairResponse
