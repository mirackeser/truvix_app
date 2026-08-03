"""Dependency providers for the copilot endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from truvix.modules.analysis.dependencies import AnalysisRepositoryDep
from truvix.modules.auth.dependencies import CurrentUserDep
from truvix.modules.copilot.repository import CopilotRepository
from truvix.modules.copilot.service import CopilotService
from truvix.modules.vehicles.dependencies import VehicleRepositoryDep
from truvix.shared.dependencies import ContainerDep, SessionDep, SettingsDep
from truvix.shared.errors import RateLimitExceededError
from truvix.shared.ratelimit import RateLimiter

_SECONDS_PER_MINUTE = 60


def get_copilot_repository(session: SessionDep) -> CopilotRepository:
    """Provide the copilot repository bound to the request's transaction."""
    return CopilotRepository(session)


CopilotRepositoryDep = Annotated[CopilotRepository, Depends(get_copilot_repository)]


def get_copilot_service(
    conversations: CopilotRepositoryDep,
    vehicles: VehicleRepositoryDep,
    analyses: AnalysisRepositoryDep,
    container: ContainerDep,
    settings: SettingsDep,
) -> CopilotService:
    """Provide the copilot service for the current request."""
    return CopilotService(
        conversations=conversations,
        vehicles=vehicles,
        analyses=analyses,
        model=container.chat_model,
        settings=settings.ai,
    )


CopilotServiceDep = Annotated[CopilotService, Depends(get_copilot_service)]


async def enforce_copilot_rate_limit(
    current_user: CurrentUserDep,
    container: ContainerDep,
    settings: SettingsDep,
) -> None:
    """Throttle message sending per account.

    Every message costs provider tokens, so this is a cost control as much as
    an abuse control. The budget is per user rather than per client address,
    because one account across two devices is still one paying context. Fails
    open: a Redis outage should not silence the copilot.

    Raises:
        RateLimitExceededError: When the account's budget is exhausted.
    """
    if not settings.rate_limit.enabled:
        return

    limiter = RateLimiter(container.redis, fail_open=True)
    result = await limiter.check(
        scope="copilot",
        identifier=str(current_user.id),
        limit=settings.ai.copilot_messages_per_minute,
        window_seconds=_SECONDS_PER_MINUTE,
    )
    if not result.allowed:
        raise RateLimitExceededError(
            "You are sending messages too quickly. Please wait a moment.",
            retry_after_seconds=result.retry_after_seconds,
        )
