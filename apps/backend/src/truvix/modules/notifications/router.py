"""HTTP endpoints for the notification centre."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Self

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, ConfigDict

from truvix.modules.auth.dependencies import CurrentUserDep
from truvix.modules.notifications.models import (
    Notification,
    NotificationCategory,
    NotificationPreference,
)
from truvix.modules.notifications.service import NotificationService
from truvix.shared.dependencies import SessionDep
from truvix.shared.errors import PROBLEM_CONTENT_TYPE
from truvix.shared.pagination import Page, PageParamsDep
from truvix.shared.schemas import StrictRequest

router = APIRouter(prefix="/notifications", tags=["notifications"])

_PROBLEM: dict[str, Any] = {"content": {PROBLEM_CONTENT_TYPE: {}}}
_UNAUTHORISED: dict[int | str, dict[str, Any]] = {
    status.HTTP_401_UNAUTHORIZED: {"description": "Access token missing or invalid.", **_PROBLEM},
}
_NOT_FOUND: dict[int | str, dict[str, Any]] = {
    **_UNAUTHORISED,
    status.HTTP_404_NOT_FOUND: {
        "description": "No such notification in this account.",
        **_PROBLEM,
    },
}


class NotificationResponse(BaseModel):
    """One notification centre entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category: NotificationCategory
    event_type: str
    title: str
    body: str
    vehicle_id: uuid.UUID | None
    read: bool
    created_at: datetime

    @classmethod
    def from_notification(cls, notification: Notification) -> Self:
        """Build the response from a persisted notification."""
        return cls(
            id=notification.id,
            category=notification.category,
            event_type=notification.event_type,
            title=notification.title,
            body=notification.body,
            vehicle_id=notification.vehicle_id,
            read=notification.is_read,
            created_at=notification.created_at,
        )


class NotificationSummaryResponse(BaseModel):
    """Counts behind the centre's tabs and the app badge."""

    total: int
    unread: int
    opportunities: int
    risks: int
    ai_suggestions: int


class PreferencesResponse(BaseModel):
    """The account's notification switches."""

    model_config = ConfigDict(from_attributes=True)

    price_changes: bool
    risk_alerts: bool
    ai_suggestions: bool
    market_updates: bool

    @classmethod
    def from_preferences(cls, preferences: NotificationPreference) -> Self:
        """Build the response from a persisted preference row."""
        return cls(
            price_changes=preferences.price_changes,
            risk_alerts=preferences.risk_alerts,
            ai_suggestions=preferences.ai_suggestions,
            market_updates=preferences.market_updates,
        )


class PreferencesUpdateRequest(StrictRequest):
    """Partial update of the notification switches."""

    price_changes: bool | None = None
    risk_alerts: bool | None = None
    ai_suggestions: bool | None = None
    market_updates: bool | None = None


class MarkAllReadResponse(BaseModel):
    """Result of a bulk mark-as-read."""

    marked: int


def _service(session: SessionDep) -> NotificationService:
    return NotificationService(session)


@router.get(
    "",
    response_model=Page[NotificationResponse],
    summary="List notifications",
    description="Returns a page of the caller's notifications, newest first.",
    responses=_UNAUTHORISED,
)
async def list_notifications(
    current_user: CurrentUserDep,
    session: SessionDep,
    params: PageParamsDep,
    category: Annotated[
        NotificationCategory | None, Query(description="Restrict to one tab.")
    ] = None,
    unread_only: Annotated[bool, Query(description="Only unread entries.")] = False,
) -> Page[NotificationResponse]:
    """List the caller's notifications."""
    notifications, total = await _service(session).list_for(
        current_user.id, category=category, unread_only=unread_only, params=params
    )
    items = [NotificationResponse.from_notification(item) for item in notifications]
    return Page[NotificationResponse].create(items=items, total=total, params=params)


@router.get(
    "/summary",
    response_model=NotificationSummaryResponse,
    summary="Tab counts",
    description="Returns the counts shown on the centre's tabs and the badge.",
    responses=_UNAUTHORISED,
)
async def read_summary(
    current_user: CurrentUserDep, session: SessionDep
) -> NotificationSummaryResponse:
    """Return the caller's notification counts."""
    counts = await _service(session).counts_for(current_user.id)
    return NotificationSummaryResponse(
        total=counts.total,
        unread=counts.unread,
        opportunities=counts.opportunities,
        risks=counts.risks,
        ai_suggestions=counts.ai_suggestions,
    )


@router.post(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    summary="Mark one as read",
    description="Marks a single notification as read; idempotent.",
    responses=_NOT_FOUND,
)
async def mark_read(
    notification_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> NotificationResponse:
    """Mark one notification as read."""
    notification = await _service(session).mark_read(current_user.id, notification_id)
    return NotificationResponse.from_notification(notification)


@router.post(
    "/read-all",
    response_model=MarkAllReadResponse,
    summary="Mark all as read",
    description="Marks every unread notification as read, optionally per tab.",
    responses=_UNAUTHORISED,
)
async def mark_all_read(
    current_user: CurrentUserDep,
    session: SessionDep,
    category: Annotated[
        NotificationCategory | None, Query(description="Restrict to one tab.")
    ] = None,
) -> MarkAllReadResponse:
    """Mark all of the caller's notifications as read."""
    marked = await _service(session).mark_all_read(current_user.id, category=category)
    return MarkAllReadResponse(marked=marked)


@router.get(
    "/preferences",
    response_model=PreferencesResponse,
    summary="Read preferences",
    description="Returns the caller's notification switches.",
    responses=_UNAUTHORISED,
)
async def read_preferences(
    current_user: CurrentUserDep, session: SessionDep
) -> PreferencesResponse:
    """Return the caller's notification preferences."""
    preferences = await _service(session).preferences_for(current_user.id)
    return PreferencesResponse.from_preferences(preferences)


@router.patch(
    "/preferences",
    response_model=PreferencesResponse,
    summary="Update preferences",
    description="Applies partial changes to the caller's notification switches.",
    responses=_UNAUTHORISED,
)
async def update_preferences(
    payload: PreferencesUpdateRequest,
    current_user: CurrentUserDep,
    session: SessionDep,
) -> PreferencesResponse:
    """Update the caller's notification preferences."""
    changes = {
        field: value
        for field, value in payload.model_dump(exclude_unset=True).items()
        if value is not None
    }
    preferences = await _service(session).update_preferences(current_user.id, changes=changes)
    return PreferencesResponse.from_preferences(preferences)
