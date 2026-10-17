"""
Defines schemas for the Copilot module.

These schemas represent the data structures used for the conversational AI assistant
that helps users understand vehicle data and make informed decisions.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Literal, Any

from pydantic import BaseModel, Field


class VehicleContext(BaseModel):
    make: str
    model: str
    model_year: int
    mileage_km: int
    fuel_type: str | None = None
    transmission: str | None = None
    price: Decimal | None = None
    currency: str = 'TRY'
    city: str | None = None
    # Optional analysis context
    trust_score: int | None = None
    risk_level: str | None = None
    analysis_summary: str | None = None
    findings: list[str] = Field(default_factory=list)


class MessageEntry(BaseModel):
    role: Literal['user', 'assistant']
    content: str


class CopilotRequest(BaseModel):
    vehicle: VehicleContext
    message: str = Field(min_length=1, max_length=4000)
    history: list[MessageEntry] = Field(default_factory=list, max_length=24)


class CopilotResponse(BaseModel):
    reply: str
    input_tokens: int = 0
    output_tokens: int = 0
