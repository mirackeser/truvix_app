"""HTTP endpoint for the home screen aggregate."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, status

from truvix.modules.analysis.dependencies import AnalysisRepositoryDep
from truvix.modules.auth.dependencies import CurrentUserDep
from truvix.modules.dashboard.schemas import DashboardResponse
from truvix.modules.dashboard.service import DashboardService
from truvix.modules.notifications.service import NotificationService
from truvix.modules.vehicles.dependencies import VehicleServiceDep
from truvix.shared.dependencies import SessionDep
from truvix.shared.errors import PROBLEM_CONTENT_TYPE

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

_PROBLEM: dict[str, Any] = {"content": {PROBLEM_CONTENT_TYPE: {}}}


def get_dashboard_service(
    vehicles: VehicleServiceDep,
    analyses: AnalysisRepositoryDep,
    session: SessionDep,
) -> DashboardService:
    """Provide the home screen aggregator for the current request."""
    return DashboardService(
        vehicles=vehicles,
        analyses=analyses,
        notifications=NotificationService(session),
    )


DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]


@router.get(
    "",
    response_model=DashboardResponse,
    summary="Home screen",
    description=(
        "Returns everything the home screen renders — garage counts, recent "
        "analyses, price drops, saved vehicles and recommendations — in one "
        "consistent snapshot."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {
            "description": "Access token missing or invalid.",
            **_PROBLEM,
        }
    },
)
async def read_dashboard(
    current_user: CurrentUserDep,
    service: DashboardServiceDep,
) -> DashboardResponse:
    """Return the caller's home screen."""
    return await service.build(current_user)
