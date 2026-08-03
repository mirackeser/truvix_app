"""Data access for analyses, their photos and findings.

As with vehicles, every read is scoped to the owning user by joining through
the vehicle. An analysis id alone can never fetch another user's report.
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from truvix.modules.analysis.models import AnalysisPhoto, RiskFinding, VehicleAnalysis
from truvix.modules.vehicles.models import Vehicle
from truvix.shared.pagination import PageParams


class AnalysisRepository:
    """Reads and writes analysis records."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the repository.

        Args:
            session: The session whose transaction this repository participates in.
        """
        self._session = session

    async def get_for_owner(
        self, *, owner_id: uuid.UUID, analysis_id: uuid.UUID
    ) -> VehicleAnalysis | None:
        """Fetch one of the owner's analyses with photos and findings loaded.

        Args:
            owner_id: The account the analysis must belong to, via its vehicle.
            analysis_id: The analysis to fetch.

        Returns:
            The analysis, or ``None`` when it does not exist or is not theirs;
            the two cases are indistinguishable by design.
        """
        statement = (
            select(VehicleAnalysis)
            .join(Vehicle, VehicleAnalysis.vehicle_id == Vehicle.id)
            .where(
                VehicleAnalysis.id == analysis_id,
                Vehicle.user_id == owner_id,
                Vehicle.deleted_at.is_(None),
            )
            .options(
                selectinload(VehicleAnalysis.photos),
                selectinload(VehicleAnalysis.findings),
                joinedload(VehicleAnalysis.vehicle),
            )
            # The analysis may already sit in the identity map with relations
            # loaded before a mutation; without this, the eager loaders would
            # not overwrite those stale collections.
            .execution_options(populate_existing=True)
        )
        analysis: VehicleAnalysis | None = await self._session.scalar(statement)
        return analysis

    async def list_for_owner(
        self, *, owner_id: uuid.UUID, params: PageParams
    ) -> tuple[Sequence[VehicleAnalysis], int]:
        """List a page of the owner's analyses, newest first.

        Args:
            owner_id: The account whose analyses to list.
            params: Pagination parameters.

        Returns:
            The page's analyses (vehicles eagerly loaded) and the total count.
        """
        base = (
            select(VehicleAnalysis)
            .join(Vehicle, VehicleAnalysis.vehicle_id == Vehicle.id)
            .where(Vehicle.user_id == owner_id, Vehicle.deleted_at.is_(None))
        )

        total = await self._session.scalar(select(func.count()).select_from(base.subquery()))

        listing = (
            base.options(joinedload(VehicleAnalysis.vehicle))
            .order_by(VehicleAnalysis.created_at.desc(), VehicleAnalysis.id.desc())
            .offset(params.offset)
            .limit(params.limit)
        )
        result = await self._session.scalars(listing)
        return result.all(), int(total or 0)

    async def photo_for_owner(
        self, *, owner_id: uuid.UUID, analysis_id: uuid.UUID, photo_id: uuid.UUID
    ) -> AnalysisPhoto | None:
        """Fetch one photo, verifying the whole ownership chain.

        Args:
            owner_id: The account the photo must belong to.
            analysis_id: The analysis the photo must be attached to.
            photo_id: The photo to fetch.
        """
        statement = (
            select(AnalysisPhoto)
            .join(VehicleAnalysis, AnalysisPhoto.analysis_id == VehicleAnalysis.id)
            .join(Vehicle, VehicleAnalysis.vehicle_id == Vehicle.id)
            .where(
                AnalysisPhoto.id == photo_id,
                AnalysisPhoto.analysis_id == analysis_id,
                Vehicle.user_id == owner_id,
                Vehicle.deleted_at.is_(None),
            )
        )
        photo: AnalysisPhoto | None = await self._session.scalar(statement)
        return photo

    async def photo_count(self, *, analysis_id: uuid.UUID) -> int:
        """Count the photos attached to an analysis.

        Args:
            analysis_id: The analysis whose photos to count.
        """
        statement = select(func.count()).where(AnalysisPhoto.analysis_id == analysis_id)
        return int(await self._session.scalar(statement) or 0)

    def add(self, analysis: VehicleAnalysis) -> None:
        """Stage a new analysis for insertion."""
        self._session.add(analysis)

    def add_photo(self, photo: AnalysisPhoto) -> None:
        """Stage a new photo record for insertion."""
        self._session.add(photo)

    def add_finding(self, finding: RiskFinding) -> None:
        """Stage a new finding for insertion."""
        self._session.add(finding)

    async def flush(self) -> None:
        """Send pending changes to the database without committing."""
        await self._session.flush()

    async def refresh_relations(self, analysis: VehicleAnalysis) -> None:
        """Reload the analysis's photos and findings after a mutation.

        Args:
            analysis: The analysis whose relations to refresh.
        """
        await self._session.refresh(analysis, attribute_names=["photos", "findings"])
