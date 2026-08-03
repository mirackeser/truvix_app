"""Persistence models for vehicle analyses, their photos and risk findings.

An analysis is a run of the evaluation engine over one garage vehicle at one
point in time. A vehicle accumulates analyses as its situation changes — new
photos, a new price, a new expertise report — and the garage screen's "Son
analiz: 2 saat önce" line falls straight out of that history.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from truvix.modules.vehicles.models import Vehicle
from truvix.shared.database import Base, TimestampMixin, UUIDPrimaryKeyMixin, pg_enum

FAILURE_REASON_MAX_LENGTH = 500
FINDING_TITLE_MAX_LENGTH = 120
FINDING_DETAIL_MAX_LENGTH = 1000
SUMMARY_MAX_LENGTH = 2000
STORAGE_KEY_MAX_LENGTH = 255
CONTENT_TYPE_MAX_LENGTH = 100
ORIGINAL_FILENAME_MAX_LENGTH = 255

MIN_SCORE = 0
MAX_SCORE = 100


class AnalysisStatus(StrEnum):
    """Lifecycle of an analysis run.

    The only legal transitions are PENDING → PROCESSING and PROCESSING →
    COMPLETED or FAILED. The service layer enforces them; nothing ever moves
    backwards, so a completed report can never silently change.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    @property
    def is_terminal(self) -> bool:
        """Whether the analysis has finished, successfully or not."""
        return self in {AnalysisStatus.COMPLETED, AnalysisStatus.FAILED}


class RiskLevel(StrEnum):
    """Banded interpretation of a trust score, as shown on the report."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class PhotoKind(StrEnum):
    """What a photo or document depicts, chosen by the uploader."""

    EXTERIOR = "exterior"
    INTERIOR = "interior"
    ENGINE = "engine"
    DASHBOARD = "dashboard"
    DAMAGE = "damage"
    DOCUMENT = "document"
    OTHER = "other"


class FindingSeverity(StrEnum):
    """Weight of a finding, mirroring the +/- markers on the risk card."""

    POSITIVE = "positive"
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class FindingCategory(StrEnum):
    """Aspect of the vehicle a finding concerns."""

    MILEAGE = "mileage"
    AGE = "age"
    DAMAGE = "damage"
    MAINTENANCE = "maintenance"
    PRICE = "price"
    DOCUMENTATION = "documentation"
    GENERAL = "general"


_ANALYSIS_STATUS = pg_enum(AnalysisStatus, name="analysis_status")
_RISK_LEVEL = pg_enum(RiskLevel, name="risk_level")
_PHOTO_KIND = pg_enum(PhotoKind, name="photo_kind")
_FINDING_SEVERITY = pg_enum(FindingSeverity, name="finding_severity")
_FINDING_CATEGORY = pg_enum(FindingCategory, name="finding_category")


class VehicleAnalysis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One evaluation run over a garage vehicle."""

    __tablename__ = "vehicle_analyses"
    __table_args__ = (
        CheckConstraint(
            f"trust_score IS NULL OR trust_score BETWEEN {MIN_SCORE} AND {MAX_SCORE}",
            name="trust_score_in_range",
        ),
        # A completed run carries its results; an unfinished one must not.
        CheckConstraint(
            "(status = 'completed') = (trust_score IS NOT NULL)",
            name="score_present_iff_completed",
        ),
        CheckConstraint(
            "(status = 'failed') = (failure_reason IS NOT NULL)",
            name="failure_reason_present_iff_failed",
        ),
        # The report list and "Son analizler" both read one vehicle's runs
        # newest-first.
        Index("ix_vehicle_analyses_vehicle_recent", "vehicle_id", text("created_at DESC")),
    )

    vehicle_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicles.id", ondelete="CASCADE"),
        nullable=False,
    )

    status: Mapped[AnalysisStatus] = mapped_column(
        _ANALYSIS_STATUS,
        nullable=False,
        default=AnalysisStatus.PENDING,
        server_default=AnalysisStatus.PENDING.value,
    )

    trust_score: Mapped[int | None] = mapped_column(Integer)
    risk_level: Mapped[RiskLevel | None] = mapped_column(_RISK_LEVEL)
    summary: Mapped[str | None] = mapped_column(Text)
    failure_reason: Mapped[str | None] = mapped_column(String(FAILURE_REASON_MAX_LENGTH))

    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    vehicle: Mapped[Vehicle] = relationship()
    photos: Mapped[list[AnalysisPhoto]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="AnalysisPhoto.created_at",
    )
    findings: Mapped[list[RiskFinding]] = relationship(
        back_populates="analysis",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RiskFinding.position",
    )

    def __repr__(self) -> str:
        return f"VehicleAnalysis(id={self.id!r}, status={self.status.value!r})"


class AnalysisPhoto(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """A photo or document attached to an analysis before it runs."""

    __tablename__ = "analysis_photos"
    __table_args__ = (
        CheckConstraint("size_bytes > 0", name="size_positive"),
        Index("ix_analysis_photos_analysis_id", "analysis_id"),
    )

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicle_analyses.id", ondelete="CASCADE"),
        nullable=False,
    )

    kind: Mapped[PhotoKind] = mapped_column(
        _PHOTO_KIND,
        nullable=False,
        default=PhotoKind.OTHER,
        server_default=PhotoKind.OTHER.value,
    )
    storage_key: Mapped[str] = mapped_column(String(STORAGE_KEY_MAX_LENGTH), nullable=False)
    content_type: Mapped[str] = mapped_column(String(CONTENT_TYPE_MAX_LENGTH), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    # Kept only for display; never used to address the file on disk.
    original_filename: Mapped[str | None] = mapped_column(String(ORIGINAL_FILENAME_MAX_LENGTH))

    analysis: Mapped[VehicleAnalysis] = relationship(back_populates="photos")

    def __repr__(self) -> str:
        return f"AnalysisPhoto(id={self.id!r}, kind={self.kind.value!r})"


class RiskFinding(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """One line of the completed report's risk factor list."""

    __tablename__ = "risk_findings"
    __table_args__ = (Index("ix_risk_findings_analysis_id", "analysis_id"),)

    analysis_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("vehicle_analyses.id", ondelete="CASCADE"),
        nullable=False,
    )

    category: Mapped[FindingCategory] = mapped_column(_FINDING_CATEGORY, nullable=False)
    severity: Mapped[FindingSeverity] = mapped_column(_FINDING_SEVERITY, nullable=False)
    title: Mapped[str] = mapped_column(String(FINDING_TITLE_MAX_LENGTH), nullable=False)
    detail: Mapped[str] = mapped_column(String(FINDING_DETAIL_MAX_LENGTH), nullable=False)
    # Preserves the engine's ordering, which places the most important first.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    analysis: Mapped[VehicleAnalysis] = relationship(back_populates="findings")

    def __repr__(self) -> str:
        return f"RiskFinding(severity={self.severity.value!r}, title={self.title!r})"
