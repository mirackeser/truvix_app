"""FastAPI dependency providers for shared infrastructure.

Route handlers declare what they need as typed parameters; this module resolves
those needs from the container stored on the application state. No handler ever
imports the container directly, which keeps the request layer testable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.shared.config import Settings
from truvix.shared.container import ApplicationContainer
from truvix.shared.events import EventBus, dispatch_pending
from truvix.shared.security import PasswordHasherService, TokenService


def get_container(request: Request) -> ApplicationContainer:
    """Return the container attached to the running application."""
    container: ApplicationContainer = request.app.state.container
    return container


ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]


def get_settings_dep(container: ContainerDep) -> Settings:
    """Return the active application configuration."""
    return container.settings


async def get_session(container: ContainerDep) -> AsyncIterator[AsyncSession]:
    """Provide a request-scoped database session inside a transaction.

    The transaction commits when the handler returns successfully and rolls back
    if it raises, so a failed request never leaves a partial write behind.

    Domain events published during the request are dispatched here, after the
    handler returns and before the commit, so their side effects are atomic
    with the change that caused them. When the handler raises, the ``yield``
    re-raises, dispatch is skipped and everything rolls back together.

    Yields:
        An open session bound to a single transaction.
    """
    async with container.database.transaction() as session:
        bus = EventBus()
        session.info["event_bus"] = bus
        # Carried on the session so event handlers can reach it: they are given
        # only the session and the event, and this is where the bus already
        # travels.
        session.info["push_sender"] = container.push_sender
        yield session
        await dispatch_pending(session, bus)


def get_event_bus(session: SessionDep) -> EventBus:
    """Return the request's event bus, shared with the session lifecycle."""
    bus: EventBus = session.info["event_bus"]
    return bus


def get_redis(container: ContainerDep) -> Redis:
    """Return the shared Redis client."""
    return container.redis


def get_password_hasher(container: ContainerDep) -> PasswordHasherService:
    """Return the password hashing service."""
    return container.password_hasher


def get_token_service(container: ContainerDep) -> TokenService:
    """Return the token issuing and verification service."""
    return container.token_service


SettingsDep = Annotated[Settings, Depends(get_settings_dep)]
EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
RedisDep = Annotated[Redis, Depends(get_redis)]
PasswordHasherDep = Annotated[PasswordHasherService, Depends(get_password_hasher)]
TokenServiceDep = Annotated[TokenService, Depends(get_token_service)]
