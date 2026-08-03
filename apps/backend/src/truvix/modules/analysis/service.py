"""Analysis workflow: creation, evidence upload, execution and reporting.

The state machine is enforced here and only here. PENDING accepts evidence and
may be started; PROCESSING may only complete or fail; terminal states accept
nothing. Reports are therefore immutable once produced — a user re-analysing a
vehicle gets a new run, never a silently rewritten old one.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import BinaryIO

from truvix.modules.analysis.engine import AnalysisEngine, EvidenceSummary
from truvix.modules.analysis.models import (
    FAILURE_REASON_MAX_LENGTH,
    AnalysisPhoto,
    AnalysisStatus,
    PhotoKind,
    RiskFinding,
    VehicleAnalysis,
)
from truvix.modules.analysis.repository import AnalysisRepository
from truvix.modules.analysis.schemas import AnalysisSummaryResponse
from truvix.modules.vehicles.repository import VehicleRepository
from truvix.shared.config import StorageSettings
from truvix.shared.errors import ConflictError, NotFoundError
from truvix.shared.logging import get_logger
from truvix.shared.pagination import Page, PageParams
from truvix.shared.storage import LocalFileStorage, sniff_upload

_logger = get_logger(__name__)


class AnalysisService:
    """Runs the analysis workflow for a user's vehicles."""

    def __init__(
        self,
        *,
        analyses: AnalysisRepository,
        vehicles: VehicleRepository,
        storage: LocalFileStorage,
        engine: AnalysisEngine,
        settings: StorageSettings,
    ) -> None:
        """Initialise the service.

        Args:
            analyses: Access to analysis records.
            vehicles: Access to vehicle records, for ownership checks.
            storage: Where uploaded evidence is persisted.
            engine: The evaluation engine to run.
            settings: Upload size and count limits.
        """
        self._analyses = analyses
        self._vehicles = vehicles
        self._storage = storage
        self._engine = engine
        self._settings = settings

    async def create(self, *, owner_id: uuid.UUID, vehicle_id: uuid.UUID) -> VehicleAnalysis:
        """Open a new analysis for one of the owner's vehicles.

        Args:
            owner_id: The account requesting the analysis.
            vehicle_id: The vehicle to analyse.

        Returns:
            The new analysis in PENDING state.

        Raises:
            NotFoundError: If the vehicle is not the owner's.
        """
        vehicle = await self._vehicles.get_for_owner(owner_id=owner_id, vehicle_id=vehicle_id)
        if vehicle is None:
            raise NotFoundError.for_resource("Vehicle", vehicle_id)

        analysis = VehicleAnalysis(vehicle_id=vehicle.id)
        self._analyses.add(analysis)
        await self._analyses.flush()

        _logger.info("analysis_created", analysis_id=str(analysis.id), vehicle_id=str(vehicle.id))
        return await self._reload(owner_id=owner_id, analysis_id=analysis.id)

    async def attach_photo(
        self,
        *,
        owner_id: uuid.UUID,
        analysis_id: uuid.UUID,
        stream: BinaryIO,
        kind: PhotoKind,
        original_filename: str | None,
    ) -> AnalysisPhoto:
        """Attach a photo or document to a pending analysis.

        The payload's type is decided by sniffing its bytes; the client's
        filename and declared content type are ignored.

        Args:
            owner_id: The account the analysis must belong to.
            analysis_id: The analysis to attach to.
            stream: The upload, positioned at the start.
            kind: What the uploader says the image depicts.
            original_filename: Kept for display only.

        Returns:
            The stored photo record.

        Raises:
            NotFoundError: If the analysis is not the owner's.
            ConflictError: If the analysis is no longer accepting evidence, or
                the photo limit is reached.
            DomainValidationError: If the payload is not a supported type or
                exceeds the size limit.
        """
        analysis = await self._require(owner_id=owner_id, analysis_id=analysis_id)
        if analysis.status is not AnalysisStatus.PENDING:
            raise ConflictError("Evidence can only be added before the analysis starts.")

        existing = await self._analyses.photo_count(analysis_id=analysis.id)
        if existing >= self._settings.max_photos_per_analysis:
            raise ConflictError(
                f"An analysis may hold at most {self._settings.max_photos_per_analysis} files."
            )

        sniffed = sniff_upload(stream)
        stored = self._storage.save(
            stream,
            namespace=str(analysis.id),
            extension=sniffed.extension,
            max_bytes=self._settings.max_upload_bytes,
        )

        photo = AnalysisPhoto(
            analysis_id=analysis.id,
            kind=kind,
            storage_key=stored.key,
            content_type=sniffed.content_type,
            size_bytes=stored.size_bytes,
            original_filename=original_filename,
        )
        self._analyses.add_photo(photo)
        await self._analyses.flush()

        _logger.info(
            "analysis_photo_attached",
            analysis_id=str(analysis.id),
            content_type=sniffed.content_type,
            size_bytes=stored.size_bytes,
        )
        return photo

    async def start(self, *, owner_id: uuid.UUID, analysis_id: uuid.UUID) -> VehicleAnalysis:
        """Run a pending analysis to completion.

        The engine is executed within the request for now: the rule-based
        engine is effectively instantaneous. The state machine is identical to
        the queued execution the AI engine will need — PENDING moves to
        PROCESSING before evaluation and to a terminal state after — so moving
        this call onto a worker changes scheduling, not semantics.

        Args:
            owner_id: The account the analysis must belong to.
            analysis_id: The analysis to run.

        Returns:
            The finished analysis with its report loaded.

        Raises:
            NotFoundError: If the analysis is not the owner's.
            ConflictError: If the analysis is not in PENDING state.
        """
        analysis = await self._require(owner_id=owner_id, analysis_id=analysis_id)
        if analysis.status is not AnalysisStatus.PENDING:
            raise ConflictError(
                f"The analysis cannot be started from its current state ({analysis.status.value})."
            )

        analysis.status = AnalysisStatus.PROCESSING
        analysis.started_at = datetime.now(UTC)
        await self._analyses.flush()

        evidence = EvidenceSummary(
            photo_count=len(analysis.photos),
            photo_kinds=frozenset(photo.kind for photo in analysis.photos),
        )

        try:
            result = await self._engine.evaluate(analysis.vehicle, evidence)
        except Exception as exc:
            analysis.status = AnalysisStatus.FAILED
            analysis.failure_reason = str(exc)[:FAILURE_REASON_MAX_LENGTH]
            analysis.completed_at = datetime.now(UTC)
            await self._analyses.flush()
            _logger.exception("analysis_failed", analysis_id=str(analysis.id))
            return await self._reload(owner_id=owner_id, analysis_id=analysis.id)

        analysis.trust_score = result.trust_score
        analysis.risk_level = result.risk_level
        analysis.summary = result.summary
        analysis.status = AnalysisStatus.COMPLETED
        analysis.completed_at = datetime.now(UTC)

        for position, finding in enumerate(result.findings):
            self._analyses.add_finding(
                RiskFinding(
                    analysis_id=analysis.id,
                    category=finding.category,
                    severity=finding.severity,
                    title=finding.title,
                    detail=finding.detail,
                    position=position,
                )
            )
        await self._analyses.flush()

        _logger.info(
            "analysis_completed",
            analysis_id=str(analysis.id),
            trust_score=result.trust_score,
            risk_level=result.risk_level.value,
        )
        return await self._reload(owner_id=owner_id, analysis_id=analysis.id)

    async def get(self, *, owner_id: uuid.UUID, analysis_id: uuid.UUID) -> VehicleAnalysis:
        """Fetch one of the owner's analyses with its full report.

        Args:
            owner_id: The account the analysis must belong to.
            analysis_id: The analysis to fetch.

        Raises:
            NotFoundError: If the analysis is not the owner's.
        """
        return await self._require(owner_id=owner_id, analysis_id=analysis_id)

    async def list(
        self, *, owner_id: uuid.UUID, params: PageParams
    ) -> Page[AnalysisSummaryResponse]:
        """List a page of the owner's analyses, newest first.

        Args:
            owner_id: The account whose analyses to list.
            params: Pagination parameters.
        """
        analyses, total = await self._analyses.list_for_owner(owner_id=owner_id, params=params)
        items = [AnalysisSummaryResponse.from_analysis(analysis) for analysis in analyses]
        return Page[AnalysisSummaryResponse].create(items=items, total=total, params=params)

    async def open_photo(
        self, *, owner_id: uuid.UUID, analysis_id: uuid.UUID, photo_id: uuid.UUID
    ) -> tuple[AnalysisPhoto, str]:
        """Resolve a photo to its record and readable file path.

        Args:
            owner_id: The account the photo must belong to.
            analysis_id: The analysis the photo is attached to.
            photo_id: The photo to open.

        Returns:
            The photo record and the absolute path of its bytes.

        Raises:
            NotFoundError: If the ownership chain does not hold, or the bytes
                are missing from storage.
        """
        photo = await self._analyses.photo_for_owner(
            owner_id=owner_id, analysis_id=analysis_id, photo_id=photo_id
        )
        if photo is None:
            raise NotFoundError.for_resource("Photo", photo_id)
        try:
            path = self._storage.open(photo.storage_key)
        except FileNotFoundError as exc:
            _logger.error(
                "analysis_photo_bytes_missing",
                photo_id=str(photo_id),
                storage_key=photo.storage_key,
            )
            raise NotFoundError.for_resource("Photo", photo_id) from exc
        return photo, str(path)

    async def _require(self, *, owner_id: uuid.UUID, analysis_id: uuid.UUID) -> VehicleAnalysis:
        """Fetch an analysis or raise if it is not the owner's."""
        analysis = await self._analyses.get_for_owner(owner_id=owner_id, analysis_id=analysis_id)
        if analysis is None:
            raise NotFoundError.for_resource("Analysis", analysis_id)
        return analysis

    async def _reload(self, *, owner_id: uuid.UUID, analysis_id: uuid.UUID) -> VehicleAnalysis:
        """Reload an analysis with fresh relations after a mutation."""
        return await self._require(owner_id=owner_id, analysis_id=analysis_id)
