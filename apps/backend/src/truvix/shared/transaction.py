"""Request-scoped database transactions.

The transaction lives in middleware rather than in a dependency, and the reason
is a correctness one rather than taste.

FastAPI runs the exit half of a ``yield`` dependency *after* the response has
been sent. With the transaction there, a client could receive ``200`` for a
write and then read its own change back as absent — the commit had not happened
yet. That is not a theoretical window: running an analysis and immediately
asking for the notifications it produces missed them roughly one time in twelve.

Middleware wraps the whole request, so the commit finishes before the response
is handed back. What the client is told happened, has happened.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from truvix.shared.events import EventBus, dispatch_pending
from truvix.shared.logging import get_logger

_logger = get_logger(__name__)

# Below this, the handler considers the request to have succeeded.
_FIRST_ERROR_STATUS = 400


class TransactionMiddleware(BaseHTTPMiddleware):
    """Opens a transaction for the request and closes it before responding."""

    def __init__(self, app: ASGIApp) -> None:
        """Initialise the middleware.

        Args:
            app: The application this wraps.
        """
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: object) -> Response:
        """Run the request inside one transaction.

        Domain events are dispatched after the handler and before the commit,
        so a change and the notification it produces land together or not at
        all.

        An error response rolls back. The exception that caused it was already
        turned into a response further in, so nothing propagates here to trigger
        a rollback on its own — and a handler that failed halfway must not leave
        its partial writes behind just because the failure was rendered politely.
        """
        container = request.app.state.container

        async with container.database.transaction() as session:
            bus = EventBus()
            session.info["event_bus"] = bus
            # Carried on the session so event handlers can reach it: they are
            # given only the session and the event.
            session.info["push_sender"] = container.push_sender
            request.state.session = session

            response: Response = await call_next(request)  # type: ignore[operator]

            if response.status_code >= _FIRST_ERROR_STATUS:
                await session.rollback()
                return response

            await dispatch_pending(session, bus)

        return response


def session_from(request: Request) -> object:
    """Return the transaction the middleware opened for this request.

    Raises:
        RuntimeError: If no transaction is in scope, which means a route was
            reached without the middleware — a wiring mistake rather than
            anything a request can cause.
    """
    session = getattr(request.state, "session", None)
    if session is None:
        raise RuntimeError(
            "No database session on the request; TransactionMiddleware is not installed."
        )
    return session
