"""Home screen aggregation.

This module composes the other modules' services rather than querying their
tables. It is a read model: it owns no schema of its own, so a change to how
the garage decides what counts as a price drop reaches the home screen without
anyone having to remember this file exists.
"""

from __future__ import annotations

from typing import Final

from truvix.modules.analysis.repository import AnalysisRepository
from truvix.modules.analysis.schemas import AnalysisSummaryResponse
from truvix.modules.dashboard.schemas import DashboardResponse, DashboardUser
from truvix.modules.notifications.service import NotificationService
from truvix.modules.users.models import User
from truvix.modules.vehicles.schemas import GarageFilter, VehicleSort
from truvix.modules.vehicles.service import VehicleService
from truvix.shared.pagination import PageParams

# Section sizes, matching how many cards the home screen shows before its
# "Tümünü Gör" link takes over.
RECENT_ANALYSES_LIMIT: Final = 5
PRICE_DROPS_LIMIT: Final = 5
SAVED_VEHICLES_LIMIT: Final = 8
RECOMMENDATIONS_LIMIT: Final = 3


class DashboardService:
    """Builds the home screen payload."""

    def __init__(
        self,
        *,
        vehicles: VehicleService,
        analyses: AnalysisRepository,
        notifications: NotificationService,
    ) -> None:
        """Initialise the service.

        Args:
            vehicles: The garage service, reused for filters and price trends.
            analyses: Access to analysis records.
            notifications: The notification service, for the unread badge.
        """
        self._vehicles = vehicles
        self._analyses = analyses
        self._notifications = notifications

    async def build(self, user: User) -> DashboardResponse:
        """Assemble the home screen for one account.

        Args:
            user: The authenticated account.
        """
        garage = await self._vehicles.garage_stats(owner_id=user.id)

        price_drops = await self._vehicles.list_garage(
            owner_id=user.id,
            garage_filter=GarageFilter.PRICE_DROPPED,
            sort=VehicleSort.RECENTLY_ADDED,
            params=PageParams(page=1, page_size=PRICE_DROPS_LIMIT),
        )
        saved = await self._vehicles.list_garage(
            owner_id=user.id,
            garage_filter=GarageFilter.FAVOURITES,
            sort=VehicleSort.RECENTLY_ADDED,
            params=PageParams(page=1, page_size=SAVED_VEHICLES_LIMIT),
        )

        recent, _total = await self._analyses.list_for_owner(
            owner_id=user.id,
            params=PageParams(page=1, page_size=RECENT_ANALYSES_LIMIT),
        )
        best = await self._analyses.best_completed_for_owner(
            owner_id=user.id, limit=RECOMMENDATIONS_LIMIT
        )
        counts = await self._notifications.counts_for(user.id)

        return DashboardResponse(
            user=DashboardUser.from_user(user),
            garage=garage,
            unread_notifications=counts.unread,
            recent_analyses=[
                AnalysisSummaryResponse.from_analysis(analysis) for analysis in recent
            ],
            price_drops=list(price_drops.items),
            saved_vehicles=[summary.vehicle for summary in saved.items],
            recommendations=[AnalysisSummaryResponse.from_analysis(analysis) for analysis in best],
        )
