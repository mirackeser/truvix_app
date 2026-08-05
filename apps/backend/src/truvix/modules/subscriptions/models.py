"""Persistence model for subscription entitlements.

An entitlement is what the App Store told us, recorded verbatim. The account's
tier is derived from it rather than being set directly, so there is exactly one
answer to "is this account premium" and it traces back to a signed transaction
Apple issued.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from truvix.shared.database import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum

PRODUCT_ID_MAX_LENGTH = 120
TRANSACTION_ID_MAX_LENGTH = 64


class EntitlementStatus(StrEnum):
    """Where a subscription stands.

    Mirrors the states the App Store reports, because inventing our own would
    mean translating twice and losing a distinction each time.
    """

    ACTIVE = "active"
    EXPIRED = "expired"
    IN_GRACE_PERIOD = "in_grace_period"
    IN_BILLING_RETRY = "in_billing_retry"
    REVOKED = "revoked"

    @property
    def grants_access(self) -> bool:
        """Whether this state entitles the account to premium features.

        A billing retry still grants access: Apple is retrying a card that may
        well succeed, and removing a paying customer's features while that
        happens loses the customer rather than saving anything.
        """
        return self in {
            EntitlementStatus.ACTIVE,
            EntitlementStatus.IN_GRACE_PERIOD,
            EntitlementStatus.IN_BILLING_RETRY,
        }


class StoreEnvironment(StrEnum):
    """Which App Store issued the transaction."""

    SANDBOX = "sandbox"
    PRODUCTION = "production"


_ENTITLEMENT_STATUS = pg_enum(EntitlementStatus, name="entitlement_status")
_STORE_ENVIRONMENT = pg_enum(StoreEnvironment, name="store_environment")


class Entitlement(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One subscription an account holds, as the App Store reports it."""

    __tablename__ = "entitlements"
    __table_args__ = (
        # Apple's original transaction id identifies a subscription across its
        # whole life, including renewals. Making it unique is what stops the
        # same purchase being redeemed on two accounts.
        UniqueConstraint("original_transaction_id", name="uq_entitlements_original_transaction_id"),
        Index("ix_entitlements_user_id", "user_id"),
        # The expiry sweep reads by expiry across all accounts.
        Index("ix_entitlements_expires_at", "expires_at"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    product_id: Mapped[str] = mapped_column(String(PRODUCT_ID_MAX_LENGTH), nullable=False)
    original_transaction_id: Mapped[str] = mapped_column(
        String(TRANSACTION_ID_MAX_LENGTH), nullable=False
    )
    #: The most recent transaction seen, so a replay of an older one is visible.
    latest_transaction_id: Mapped[str] = mapped_column(
        String(TRANSACTION_ID_MAX_LENGTH), nullable=False
    )

    status: Mapped[EntitlementStatus] = mapped_column(_ENTITLEMENT_STATUS, nullable=False)
    environment: Mapped[StoreEnvironment] = mapped_column(_STORE_ENVIRONMENT, nullable=False)

    purchased_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def is_current(self, *, now: datetime | None = None) -> bool:
        """Whether this entitlement grants access at the given moment.

        Both conditions matter. A status may still read active while the expiry
        has passed, because nothing tells us the moment it lapses — Apple's
        notification may be late or lost, so the date is checked too.

        Args:
            now: The instant to judge against. Defaults to the real clock.
        """
        moment = now or datetime.now(UTC)
        if self.revoked_at is not None:
            return False
        if not self.status.grants_access:
            return False
        return self.expires_at is None or self.expires_at > moment

    def __repr__(self) -> str:
        return f"Entitlement(product_id={self.product_id!r}, status={self.status.value!r})"
