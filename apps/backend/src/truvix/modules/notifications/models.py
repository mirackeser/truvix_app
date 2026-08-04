"""Persistence models for the notification centre and its preferences."""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column

from truvix.shared.database import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum

TITLE_MAX_LENGTH = 150
BODY_MAX_LENGTH = 500
EVENT_TYPE_MAX_LENGTH = 40


class NotificationCategory(StrEnum):
    """Tab the notification centre files a notification under."""

    OPPORTUNITY = "opportunity"
    RISK = "risk"
    AI_SUGGESTION = "ai_suggestion"
    SYSTEM = "system"


_NOTIFICATION_CATEGORY = pg_enum(NotificationCategory, name="notification_category")


class Notification(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One entry in a user's notification centre."""

    __tablename__ = "notifications"
    __table_args__ = (
        # The centre reads one user's feed newest-first, with a category filter.
        Index("ix_notifications_user_recent", "user_id", text("created_at DESC")),
        # Unread badge counts scan only unread rows.
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[NotificationCategory] = mapped_column(_NOTIFICATION_CATEGORY, nullable=False)
    # Machine-readable origin, such as "price_drop"; lets the client deep-link.
    event_type: Mapped[str] = mapped_column(String(EVENT_TYPE_MAX_LENGTH), nullable=False)
    title: Mapped[str] = mapped_column(String(TITLE_MAX_LENGTH), nullable=False)
    body: Mapped[str] = mapped_column(String(BODY_MAX_LENGTH), nullable=False)

    # The vehicle the notification is about; kept when the vehicle is removed
    # so the history still reads sensibly.
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
    )
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    @property
    def is_read(self) -> bool:
        """Whether the user has opened or dismissed this notification."""
        return self.read_at is not None

    def __repr__(self) -> str:
        return f"Notification(category={self.category.value!r}, title={self.title!r})"


class NotificationPreference(Base, TimestampMixin):
    """A user's per-category notification switches, one row per account.

    Field names mirror the settings screen: price changes, risk alerts, AI
    suggestions and market updates, each independently toggleable.
    """

    __tablename__ = "notification_preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    price_changes: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    risk_alerts: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    ai_suggestions: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )
    market_updates: Mapped[bool] = mapped_column(
        nullable=False, default=True, server_default=text("true")
    )

    def __repr__(self) -> str:
        return f"NotificationPreference(user_id={self.user_id!r})"
