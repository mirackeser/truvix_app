"""Aggregation of every versioned API router.

Feature modules expose a router; this module is the single place that decides
which of them are mounted and under which path. Keeping that decision here means
adding a module never requires editing the application factory.
"""

from __future__ import annotations

from fastapi import APIRouter

from truvix.modules.analysis.router import router as analyses_router
from truvix.modules.auth.router import router as auth_router
from truvix.modules.copilot.router import router as copilot_router
from truvix.modules.dashboard.router import router as dashboard_router
from truvix.modules.notifications.router import router as notifications_router
from truvix.modules.subscriptions.router import router as subscriptions_router
from truvix.modules.vehicles.router import collections_router
from truvix.modules.vehicles.router import router as vehicles_router


def build_api_v1_router() -> APIRouter:
    """Build the router carrying every version 1 endpoint.

    Returns:
        A router intended to be mounted under the configured v1 prefix.
    """
    router = APIRouter()
    router.include_router(auth_router)
    router.include_router(dashboard_router)
    router.include_router(vehicles_router)
    router.include_router(collections_router)
    router.include_router(analyses_router)
    router.include_router(copilot_router)
    router.include_router(notifications_router)
    router.include_router(subscriptions_router)
    return router
