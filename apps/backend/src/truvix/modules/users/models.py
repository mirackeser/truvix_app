"""Persistence model for user accounts."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from truvix.shared.database import (
    Base,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDPrimaryKeyMixin,
    pg_enum,
)

if TYPE_CHECKING:
    from truvix.modules.auth.models import RefreshToken

# Chosen to hold the longest addresses seen in practice without truncation.
EMAIL_MAX_LENGTH = 320
# E.164 permits at most 15 digits; the extra characters allow the leading plus.
PHONE_MAX_LENGTH = 16
FULL_NAME_MAX_LENGTH = 120
# Argon2id encoded hashes are well under this, with room for stronger parameters.
PASSWORD_HASH_MAX_LENGTH = 255


class UserStatus(StrEnum):
    """Lifecycle state of an account."""

    ACTIVE = "active"
    SUSPENDED = "suspended"

    @property
    def can_authenticate(self) -> bool:
        """Whether an account in this state may sign in."""
        return self is UserStatus.ACTIVE


class SubscriptionTier(StrEnum):
    """Commercial plan the account is on."""

    FREE = "free"
    PREMIUM = "premium"


class User(Base, UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin):
    """A registered Truvix account.

    Email is stored already normalised to lowercase by the service layer, so a
    plain unique constraint is enough to make addresses case-insensitively
    unique without needing a functional index.
    """

    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "failed_login_attempts >= 0",
            name="failed_login_attempts_non_negative",
        ),
        CheckConstraint(
            "phone_number IS NULL OR phone_number ~ '^\\+[1-9][0-9]{7,14}$'",
            name="phone_number_is_e164",
        ),
        # Partial index: only live accounts need fast email lookup, and it keeps
        # soft-deleted rows from bloating the index.
        Index(
            "ix_users_email_active",
            "email",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
        ),
        Index(
            "ix_users_phone_number_active",
            "phone_number",
            unique=True,
            postgresql_where=text("deleted_at IS NULL AND phone_number IS NOT NULL"),
        ),
    )

    email: Mapped[str] = mapped_column(String(EMAIL_MAX_LENGTH), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(PHONE_MAX_LENGTH), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(PASSWORD_HASH_MAX_LENGTH), nullable=False)
    full_name: Mapped[str] = mapped_column(String(FULL_NAME_MAX_LENGTH), nullable=False)

    status: Mapped[UserStatus] = mapped_column(
        pg_enum(UserStatus, name="user_status"),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )
    subscription_tier: Mapped[SubscriptionTier] = mapped_column(
        pg_enum(SubscriptionTier, name="subscription_tier"),
        nullable=False,
        default=SubscriptionTier.FREE,
        server_default=SubscriptionTier.FREE.value,
    )

    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Access tokens issued before this instant are refused.
    #:
    #: Revoking refresh tokens does not stop an access token that is already in
    #: somebody's hands: it is a signed JWT with its own lifetime and nothing
    #: consults the database to accept it. That is fine for signing out, and not
    #: fine for a password reset, where the point may be to remove a stranger
    #: from the account and half an hour of continued access is the whole
    #: problem. Setting this makes every token older than the reset invalid at
    #: once.
    tokens_invalid_before: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    refresh_tokens: Mapped[list[RefreshToken]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    @property
    def is_email_verified(self) -> bool:
        """Whether the account's email address has been confirmed."""
        return self.email_verified_at is not None

    @property
    def is_premium(self) -> bool:
        """Whether the account has access to premium-only capabilities."""
        return self.subscription_tier is SubscriptionTier.PREMIUM

    def __repr__(self) -> str:
        return f"User(id={self.id!r}, status={self.status.value!r})"
