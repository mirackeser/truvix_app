"""Response models for the home screen aggregate."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel

from truvix.modules.analysis.schemas import AnalysisSummaryResponse
from truvix.modules.users.models import SubscriptionTier, User
from truvix.modules.vehicles.schemas import (
    GarageStatsResponse,
    VehicleResponse,
    VehicleSummaryResponse,
)


class DashboardUser(BaseModel):
    """The greeting line and the premium banner's state."""

    full_name: str
    subscription_tier: SubscriptionTier
    is_premium: bool

    @classmethod
    def from_user(cls, user: User) -> Self:
        """Build the greeting from the authenticated account."""
        return cls(
            full_name=user.full_name,
            subscription_tier=user.subscription_tier,
            is_premium=user.is_premium,
        )


class DashboardResponse(BaseModel):
    """Everything the home screen renders, in one payload.

    The screen shows five sections at once. Serving them from one endpoint
    keeps the first paint to a single round trip and, more importantly, makes
    the sections mutually consistent: split across five calls, a vehicle could
    appear in "saved" and vanish from "price drops" between requests.
    """

    user: DashboardUser
    garage: GarageStatsResponse
    unread_notifications: int
    recent_analyses: list[AnalysisSummaryResponse]
    price_drops: list[VehicleSummaryResponse]
    saved_vehicles: list[VehicleResponse]
    recommendations: list[AnalysisSummaryResponse]
