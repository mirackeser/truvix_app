"""FastAPI dependency providers for shared infrastructure.

Route handlers declare what they need as typed parameters; this module resolves
those needs from the container stored on the application state. No handler ever
imports the container directly, which keeps the request layer testable.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.shared.config import Settings
from truvix.shared.container import ApplicationContainer
from truvix.shared.events import EventBus
from truvix.shared.security import PasswordHasherService, TokenService


def get_container(request: Request) -> ApplicationContainer:
    """Return the container attached to the running application."""
    container: ApplicationContainer = request.app.state.container
    return container


ContainerDep = Annotated[ApplicationContainer, Depends(get_container)]


def get_settings_dep(container: ContainerDep) -> Settings:
    """Return the active application configuration."""
    return container.settings


def get_session(request: Request) -> AsyncSession:
    """Return the transaction the middleware opened for this request.

    The transaction itself lives in :class:`TransactionMiddleware`, not here.
    FastAPI runs the exit half of a ``yield`` dependency after the response has
    been sent, so a transaction closed here would commit *after* the client had
    already been told the write succeeded — and a client that immediately read
    its own change back could find it missing.

    Returns:
        The session bound to this request's transaction.
    """
    session: AsyncSession = request.state.session
    return session


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
