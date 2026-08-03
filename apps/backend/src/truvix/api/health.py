"""Liveness and readiness probes.

The two probes answer different questions and must not be merged. Liveness asks
"is this process healthy enough to keep running?" — a failure means restart me.
Readiness asks "can this process serve traffic right now?" — a failure means
take me out of the load balancer but leave me alone, because a database blip
should not trigger a restart storm across every replica.
"""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from truvix import __version__
from truvix.shared.dependencies import ContainerDep

router = APIRouter(tags=["health"])


class LivenessResponse(BaseModel):
    """Result of a liveness probe."""

    status: Literal["alive"]
    version: Annotated[str, Field(description="Running application version.")]


class DependencyStatus(BaseModel):
    """Reachability of a single downstream dependency."""

    name: Annotated[str, Field(description="Dependency identifier.")]
    healthy: Annotated[bool, Field(description="Whether the dependency responded.")]


class ReadinessResponse(BaseModel):
    """Result of a readiness probe."""

    status: Literal["ready", "degraded"]
    version: Annotated[str, Field(description="Running application version.")]
    dependencies: list[DependencyStatus]


@router.get(
    "/health/live",
    response_model=LivenessResponse,
    summary="Liveness probe",
    description="Confirms the process is running. Does not touch dependencies.",
)
async def liveness() -> LivenessResponse:
    """Report that the process itself is alive."""
    return LivenessResponse(status="alive", version=__version__)


@router.get(
    "/health/ready",
    response_model=ReadinessResponse,
    summary="Readiness probe",
    description="Verifies every downstream dependency is reachable.",
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {
            "description": "At least one dependency is unreachable.",
            "model": ReadinessResponse,
        }
    },
)
async def readiness(container: ContainerDep, response: Response) -> ReadinessResponse:
    """Report whether the service can currently serve traffic."""
    dependencies = [
        DependencyStatus(name="postgresql", healthy=await container.database.ping()),
        DependencyStatus(name="redis", healthy=await container.ping_redis()),
    ]
    all_healthy = all(dependency.healthy for dependency in dependencies)

    if not all_healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return ReadinessResponse(
        status="ready" if all_healthy else "degraded",
        version=__version__,
        dependencies=dependencies,
    )
