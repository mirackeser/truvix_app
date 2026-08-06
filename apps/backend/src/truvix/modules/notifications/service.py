"""Notification centre logic: creation from events, reading and preferences."""

from __future__ import annotations

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import CursorResult, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.modules.notifications.devices import DeviceRegistry
from truvix.modules.notifications.models import (
    Notification,
    NotificationCategory,
    NotificationPreference,
)
from truvix.shared.errors import NotFoundError
from truvix.shared.logging import get_logger
from truvix.shared.pagination import PageParams

_logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class NotificationCounts:
    """Totals backing the notification centre's tabs and badge."""

    total: int
    unread: int
    opportunities: int
    risks: int
    ai_suggestions: int


class NotificationService:
    """Creates, lists and updates a user's notifications and preferences."""

    def __init__(self, session: AsyncSession, devices: DeviceRegistry | None = None) -> None:
        """Initialise the service.

        Args:
            session: The session whose transaction this service participates in.
            devices: Where to push a new notification. Optional because reading
                and marking notifications needs no push, and a caller that only
                does those should not have to supply one.
        """
        self._session = session
        self._devices = devices

    async def preferences_for(self, user_id: uuid.UUID) -> NotificationPreference:
        """Return the user's preferences, creating defaults on first access.

        Args:
            user_id: The account whose preferences to read.
        """
        existing = await self._session.get(NotificationPreference, user_id)
        if existing is not None:
            return existing
        created = NotificationPreference(user_id=user_id)
        self._session.add(created)
        await self._session.flush()
        return created

    async def update_preferences(
        self, user_id: uuid.UUID, *, changes: dict[str, bool]
    ) -> NotificationPreference:
        """Apply preference toggles.

        Args:
            user_id: The account whose preferences to change.
            changes: Field-to-value map, already schema-validated.
        """
        preferences = await self.preferences_for(user_id)
        for field, value in changes.items():
            setattr(preferences, field, value)
        await self._session.flush()
        return preferences

    async def record(
        self,
        *,
        user_id: uuid.UUID,
        category: NotificationCategory,
        event_type: str,
        title: str,
        body: str,
        vehicle_id: uuid.UUID | None,
    ) -> Notification:
        """Create one notification.

        Args:
            user_id: The recipient.
            category: The tab the notification files under.
            event_type: Machine-readable origin for client deep-linking.
            title: Short heading, as shown in the list.
            body: One or two sentences of detail.
            vehicle_id: The vehicle the notification concerns, if any.
        """
        notification = Notification(
            user_id=user_id,
            category=category,
            event_type=event_type,
            title=title,
            body=body,
            vehicle_id=vehicle_id,
        )
        self._session.add(notification)
        await self._session.flush()
        _logger.info("notification_recorded", category=category.value, event_type=event_type)

        if self._devices is not None:
            # Best effort, and deliberately after the flush: the notification is
            # readable in the app whether or not the push lands, and a failed
            # push must not undo the thing it was announcing.
            counts = await self.counts_for(user_id)
            await self._devices.push(notification, unread=counts.unread)

        return notification

    async def list_for(
        self,
        user_id: uuid.UUID,
        *,
        category: NotificationCategory | None,
        unread_only: bool,
        params: PageParams,
    ) -> tuple[Sequence[Notification], int]:
        """List a page of the user's notifications, newest first.

        Args:
            user_id: The account whose feed to read.
            category: Restrict to one tab, or ``None`` for all.
            unread_only: Whether to return only unread entries.
            params: Pagination parameters.
        """
        base = select(Notification).where(Notification.user_id == user_id)
        if category is not None:
            base = base.where(Notification.category == category)
        if unread_only:
            base = base.where(Notification.read_at.is_(None))

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))
        listing = (
            base.order_by(Notification.created_at.desc(), Notification.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        result = await self._session.scalars(listing)
        return result.all(), int(total or 0)

    async def counts_for(self, user_id: uuid.UUID) -> NotificationCounts:
        """Count the user's notifications per tab in one query.

        Args:
            user_id: The account whose feed to count.
        """
        statement = select(
            func.count().label("total"),
            func.count().filter(Notification.read_at.is_(None)).label("unread"),
            func.count()
            .filter(Notification.category == NotificationCategory.OPPORTUNITY)
            .label("opportunities"),
            func.count().filter(Notification.category == NotificationCategory.RISK).label("risks"),
            func.count()
            .filter(Notification.category == NotificationCategory.AI_SUGGESTION)
            .label("ai_suggestions"),
        ).where(Notification.user_id == user_id)
        row = (await self._session.execute(statement)).one()
        return NotificationCounts(
            total=row.total,
            unread=row.unread,
            opportunities=row.opportunities,
            risks=row.risks,
            ai_suggestions=row.ai_suggestions,
        )

    async def mark_read(self, user_id: uuid.UUID, notification_id: uuid.UUID) -> Notification:
        """Mark one of the user's notifications as read.

        Args:
            user_id: The account the notification must belong to.
            notification_id: The notification to mark.

        Raises:
            NotFoundError: If the notification is not the user's.
        """
        statement = select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user_id
        )
        notification: Notification | None = await self._session.scalar(statement)
        if notification is None:
            raise NotFoundError.for_resource("Notification", notification_id)
        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)
            await self._session.flush()
        return notification

    async def mark_all_read(
        self, user_id: uuid.UUID, *, category: NotificationCategory | None = None
    ) -> int:
        """Mark every unread notification as read, optionally per tab.

        Args:
            user_id: The account whose feed to update.
            category: Restrict to one tab, or ``None`` for all.

        Returns:
            How many notifications were marked.
        """
        statement = (
            update(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=datetime.now(UTC))
        )
        if category is not None:
            statement = statement.where(Notification.category == category)
        result: CursorResult[None] = await self._session.execute(statement)  # type: ignore[assignment]
        await self._session.flush()
        return result.rowcount
