"""Structured logging configuration.

All logs are emitted through structlog so that every record carries the same
machine-parseable shape. Request-scoped values such as the request id and the
authenticated user id are bound into structlog's context variables by middleware,
which means handlers and services never have to thread them through call sites.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, Processor, WrappedLogger

from truvix.shared.config import LogFormat, ObservabilitySettings

# Loggers that are noisy by default and would otherwise duplicate our access log.
_NOISY_LOGGERS = ("uvicorn.access", "sqlalchemy.engine.Engine")

# Keys whose values must never reach a log sink in readable form.
_REDACTED_KEYS = frozenset(
    {
        "password",
        "new_password",
        "current_password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "secret_key",
        "api_key",
    }
)

_REDACTION_PLACEHOLDER = "[redacted]"


def _redact_sensitive_values(
    _logger: WrappedLogger, _method_name: str, event_dict: EventDict
) -> EventDict:
    """Replace credential-bearing values with a placeholder before rendering.

    Acts as a safety net: even if a caller accidentally binds a password or token
    to a log record, the value never reaches the log sink.
    """
    for key in event_dict:
        if key.lower() in _REDACTED_KEYS and event_dict[key] is not None:
            event_dict[key] = _REDACTION_PLACEHOLDER
    return event_dict


def _build_processor_chain(log_format: LogFormat) -> list[Processor]:
    """Assemble the processor pipeline shared by structlog and stdlib logging."""
    shared: list[Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        _redact_sensitive_values,
    ]
    if log_format is LogFormat.JSON:
        shared.append(structlog.processors.format_exc_info)
    else:
        shared.append(structlog.processors.ExceptionPrettyPrinter())
    return shared


def _build_renderer(log_format: LogFormat) -> Processor:
    """Return the final processor that turns an event dict into output text."""
    if log_format is LogFormat.JSON:
        return structlog.processors.JSONRenderer()
    return structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())


def configure_logging(settings: ObservabilitySettings) -> None:
    """Configure structlog and route the standard library through it.

    Safe to call more than once; the last call wins. Both structlog loggers and
    third-party loggers that use ``logging`` end up in the same output format.

    Args:
        settings: Observability configuration controlling level and format.
    """
    shared_processors = _build_processor_chain(settings.log_format)

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared_processors,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            _build_renderer(settings.log_format),
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(settings.log_level)

    for logger_name in _NOISY_LOGGERS:
        logging.getLogger(logger_name).propagate = False


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    """Return a bound logger for the given module name.

    Args:
        name: Logger name, conventionally the calling module's ``__name__``.
    """
    return structlog.stdlib.get_logger(name)


def bind_request_context(**values: Any) -> None:
    """Bind request-scoped values onto every subsequent log record."""
    structlog.contextvars.bind_contextvars(**values)


def clear_request_context() -> None:
    """Clear request-scoped log context at the end of a request."""
    structlog.contextvars.clear_contextvars()
