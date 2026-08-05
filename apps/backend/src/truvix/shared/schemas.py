"""Shared request and response base models."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class StrictRequest(BaseModel):
    """Base for every request body the API accepts.

    Unknown fields are rejected rather than ignored. Silently dropping them
    hides a client bug — a typo'd field name looks like it worked — and it
    means any field added to a model later becomes settable the moment it
    exists, which is the shape a mass-assignment flaw takes.
    """

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
