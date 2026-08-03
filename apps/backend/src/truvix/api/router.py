"""Aggregation of every versioned API router.

Feature modules expose a router; this module is the single place that decides
which of them are mounted and under which path. Keeping that decision here means
adding a module never requires editing the application factory.
"""

from __future__ import annotations

from fastapi import APIRouter


def build_api_v1_router() -> APIRouter:
    """Build the router carrying every version 1 endpoint.

    Returns:
        A router intended to be mounted under the configured v1 prefix.
    """
    return APIRouter()
