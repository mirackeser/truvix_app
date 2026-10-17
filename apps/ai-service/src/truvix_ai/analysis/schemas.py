from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, Field


class PhotoKind(StrEnum):
    EXTERIOR = 'exterior'
    INTERIOR = 'interior'
    ENGINE = 'engine'
    DASHBOARD = 'dashboard'
    DAMAGE = 'damage'
    DOCUMENT = 'document'


class FindingSeverity(StrEnum):
    POSITIVE = 'positive'
    INFO = 'info'
    WARNING = 'warning'
    CRITICAL = 'critical'


class FindingCategory(StrEnum):
    AGE = 'age'
    MILEAGE = 'mileage'
    DAMAGE = 'damage'
    MAINTENANCE = 'maintenance'
    DOCUMENTATION = 'documentation'
    GENERAL = 'general'


class RiskLevel(StrEnum):
    LOW = 'low'
    MEDIUM = 'medium'
    HIGH = 'high'


class VehicleData(BaseModel):
    make: str
    model: str
    model_year: int = Field(ge=1900, le=2030)
    mileage_km: int = Field(ge=0)
    fuel_type: str | None = None
    transmission: str | None = None
    body_type: str | None = None
    price: Decimal | None = None
    currency: str = 'TRY'
    city: str | None = None
    vin: str | None = None  # never sent to LLM
    plate: str | None = None  # never sent to LLM


class PhotoInput(BaseModel):
    data_b64: str
    media_type: str = 'image/jpeg'
    kind: PhotoKind = PhotoKind.EXTERIOR


class RiskFindingOut(BaseModel):
    category: FindingCategory
    severity: FindingSeverity
    title: str
    detail: str


class AnalysisRequest(BaseModel):
    vehicle: VehicleData
    photos: list[PhotoInput] = Field(default_factory=list, max_length=12)


class AnalysisResponse(BaseModel):
    trust_score: int = Field(ge=0, le=100)
    risk_level: RiskLevel
    summary: str
    findings: list[RiskFindingOut]
    images_inspected: int = 0
    ai_enhanced: bool = False
