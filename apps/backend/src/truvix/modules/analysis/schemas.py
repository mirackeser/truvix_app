"""Request and response models for the analysis endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field

from truvix.modules.analysis.models import (
    AnalysisPhoto,
    AnalysisStatus,
    FindingCategory,
    FindingSeverity,
    PhotoKind,
    RiskFinding,
    RiskLevel,
    VehicleAnalysis,
)


class AnalysisPhotoResponse(BaseModel):
    """One photo or document attached to an analysis."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    kind: PhotoKind
    content_type: str
    size_bytes: int
    original_filename: str | None
    created_at: datetime

    @classmethod
    def from_photo(cls, photo: AnalysisPhoto) -> Self:
        """Build the response from a persisted photo record."""
        return cls(
            id=photo.id,
            kind=photo.kind,
            content_type=photo.content_type,
            size_bytes=photo.size_bytes,
            original_filename=photo.original_filename,
            created_at=photo.created_at,
        )


class RiskFindingResponse(BaseModel):
    """One line of the report's risk factor list."""

    model_config = ConfigDict(from_attributes=True)

    category: FindingCategory
    severity: FindingSeverity
    title: str
    detail: str

    @classmethod
    def from_finding(cls, finding: RiskFinding) -> Self:
        """Build the response from a persisted finding."""
        return cls(
            category=finding.category,
            severity=finding.severity,
            title=finding.title,
            detail=finding.detail,
        )


class AnalysisResponse(BaseModel):
    """Full view of one analysis run, including its report when completed."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    vehicle_id: uuid.UUID
    status: AnalysisStatus
    trust_score: Annotated[int | None, Field(ge=0, le=100)]
    risk_level: RiskLevel | None
    summary: str | None
    failure_reason: str | None
    photos: list[AnalysisPhotoResponse]
    findings: list[RiskFindingResponse]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_analysis(cls, analysis: VehicleAnalysis) -> Self:
        """Build the response from a persisted analysis with loaded relations."""
        return cls(
            id=analysis.id,
            vehicle_id=analysis.vehicle_id,
            status=analysis.status,
            trust_score=analysis.trust_score,
            risk_level=analysis.risk_level,
            summary=analysis.summary,
            failure_reason=analysis.failure_reason,
            photos=[AnalysisPhotoResponse.from_photo(photo) for photo in analysis.photos],
            findings=[RiskFindingResponse.from_finding(finding) for finding in analysis.findings],
            created_at=analysis.created_at,
            started_at=analysis.started_at,
            completed_at=analysis.completed_at,
        )


class AnalysisSummaryResponse(BaseModel):
    """Compact view used by analysis lists and the home screen cards."""

    id: uuid.UUID
    vehicle_id: uuid.UUID
    vehicle_display_name: str
    status: AnalysisStatus
    trust_score: int | None
    risk_level: RiskLevel | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def from_analysis(cls, analysis: VehicleAnalysis) -> Self:
        """Build the summary from a persisted analysis with its vehicle loaded."""
        return cls(
            id=analysis.id,
            vehicle_id=analysis.vehicle_id,
            vehicle_display_name=analysis.vehicle.display_name,
            status=analysis.status,
            trust_score=analysis.trust_score,
            risk_level=analysis.risk_level,
            created_at=analysis.created_at,
            completed_at=analysis.completed_at,
        )
