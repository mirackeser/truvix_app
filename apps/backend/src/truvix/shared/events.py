"""In-process domain events, dispatched inside the request transaction.

Services publish plain frozen dataclasses to a request-scoped bus; after the
handler returns, the session dependency dispatches them to registered handlers
using the same session. The side effects therefore commit atomically with the
change that caused them: a price drop and its notification either both persist
or neither does. A failing handler is logged and skipped, because a broken
notification must never fail the user's action.

Events carry only primitive fields, so publishing modules and subscribing
modules share these definitions without importing each other.
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from truvix.shared.logging import get_logger

_logger = get_logger(__name__)

# Cap on cascade depth, so handlers that publish further events cannot loop.
_MAX_DISPATCH_ROUNDS = 5


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """Base class for every domain event."""


@dataclass(frozen=True, slots=True)
class PriceDropped(DomainEvent):
    """A tracked vehicle's asking price fell."""

    user_id: uuid.UUID
    vehicle_id: uuid.UUID
    vehicle_name: str
    previous_price: Decimal
    new_price: Decimal


@dataclass(frozen=True, slots=True)
class AnalysisCompleted(DomainEvent):
    """An analysis run finished with a report."""

    user_id: uuid.UUID
    vehicle_id: uuid.UUID
    analysis_id: uuid.UUID
    vehicle_name: str
    trust_score: int
    risk_level: str


type EventHandler = Callable[[AsyncSession, DomainEvent], Awaitable[None]]


class HandlerRegistry:
    """Process-wide mapping from event type to its handlers."""

    def __init__(self) -> None:
        self._handlers: dict[type[DomainEvent], list[EventHandler]] = defaultdict(list)

    def register(self, event_type: type[DomainEvent], handler: EventHandler) -> None:
        """Attach a handler to an event type; duplicate registrations are ignored.

        Args:
            event_type: The event class to subscribe to.
            handler: Coroutine invoked with the session and the event.
        """
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    def handlers_for(self, event_type: type[DomainEvent]) -> list[EventHandler]:
        """Return the handlers subscribed to an event type."""
        return list(self._handlers.get(event_type, ()))


# The application's single registry; populated once at startup.
registry = HandlerRegistry()


class EventBus:
    """Request-scoped collector of published events."""

    def __init__(self) -> None:
        self._pending: list[DomainEvent] = []

    def publish(self, event: DomainEvent) -> None:
        """Queue an event for dispatch at the end of the request.

        Args:
            event: The event to record.
        """
        self._pending.append(event)

    def drain(self) -> list[DomainEvent]:
        """Remove and return every queued event."""
        drained, self._pending = self._pending, []
        return drained


async def dispatch_pending(session: AsyncSession, bus: EventBus) -> None:
    """Run every registered handler for the bus's queued events.

    Handlers may publish follow-up events, which are dispatched in further
    rounds up to a fixed depth. Handler failures are logged and swallowed.

    Args:
        session: The request's session, shared with the handlers.
        bus: The bus whose events to dispatch.
    """
    for _round in range(_MAX_DISPATCH_ROUNDS):
        events = bus.drain()
        if not events:
            return
        for event in events:
            for handler in registry.handlers_for(type(event)):
                try:
                    await handler(session, event)
                except Exception:
                    _logger.exception(
                        "event_handler_failed",
                        event_type=type(event).__name__,
                        handler=getattr(handler, "__qualname__", repr(handler)),
                    )
    if bus.drain():
        _logger.error("event_dispatch_depth_exceeded")
