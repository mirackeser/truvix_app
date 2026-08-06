"""Transactional email delivery."""

from truvix.shared.email.sender import (
    Email,
    EmailSender,
    LoggingEmailSender,
    SMTPEmailSender,
    build_email_sender,
)

__all__ = [
    "Email",
    "EmailSender",
    "LoggingEmailSender",
    "SMTPEmailSender",
    "build_email_sender",
]
