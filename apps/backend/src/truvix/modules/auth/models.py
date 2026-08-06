"""Persistence models for sessions and email verification.

Each row is one issued refresh token, keyed by the ``jti`` embedded in the JWT.
Rotation links tokens into a chain, which is what makes stolen-token detection
possible: presenting an already-rotated token proves two parties hold the same
credential, so the whole chain is revoked.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import Mapped, mapped_column, relationship

from truvix.shared.database import Base, TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from truvix.modules.users.models import User

USER_AGENT_MAX_LENGTH = 400


class RefreshToken(Base, TimestampMixin):
    """A single issued refresh token and its rotation state."""

    __tablename__ = "refresh_tokens"
    __table_args__ = (
        # Revoking a chain and listing a user's sessions both scan by user; the
        # partial predicate keeps the index to tokens that can still be used.
        Index(
            "ix_refresh_tokens_user_id_active",
            "user_id",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        # Supports the scheduled purge of tokens that are past their usefulness.
        Index("ix_refresh_tokens_expires_at", "expires_at"),
    )

    # The token's jti claim, so a presented JWT maps straight to its row.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Set when this token is rotated, forming the chain used for reuse detection.
    replaced_by_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("refresh_tokens.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Captured so a user can recognise and revoke an unfamiliar session.
    user_agent: Mapped[str | None] = mapped_column(String(USER_AGENT_MAX_LENGTH))
    ip_address: Mapped[str | None] = mapped_column(INET)

    user: Mapped[User] = relationship(back_populates="refresh_tokens")

    @property
    def is_revoked(self) -> bool:
        """Whether the token has been explicitly invalidated."""
        return self.revoked_at is not None

    def is_expired(self, *, now: datetime) -> bool:
        """Whether the token is past its expiry.

        Args:
            now: The current time, supplied so callers control the clock.
        """
        return self.expires_at <= now

    def is_usable(self, *, now: datetime) -> bool:
        """Whether the token may still be exchanged for a new pair.

        Args:
            now: The current time, supplied so callers control the clock.
        """
        return not self.is_revoked and not self.is_expired(now=now)

    def __repr__(self) -> str:
        return f"RefreshToken(id={self.id!r}, user_id={self.user_id!r}, revoked={self.is_revoked})"


TOKEN_HASH_LENGTH = 64


class EmailVerificationToken(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A one-time link proving somebody can read the address they signed up with.

    The token is stored as a digest, never in the clear: a leaked database
    should not also hand over the ability to verify every address in it.
    """

    __tablename__ = "email_verification_tokens"
    __table_args__ = (
        # The lookup on redemption is by digest, and only one token may exist
        # per digest for a redemption to be unambiguous.
        UniqueConstraint("token_hash", name="uq_email_verification_tokens_token_hash"),
        # Issuing a new token deletes the account's old ones.
        Index("ix_email_verification_tokens_user_id", "user_id"),
        # The purge reads by expiry across all accounts.
        Index("ix_email_verification_tokens_expires_at", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(TOKEN_HASH_LENGTH), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        # Deliberately omits the digest: a repr ends up in logs and tracebacks.
        return f"EmailVerificationToken(user_id={self.user_id!r})"
