"""Dependency providers for the analysis endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from truvix.modules.analysis.engine import RuleBasedEngine
from truvix.modules.analysis.repository import AnalysisRepository
from truvix.modules.analysis.service import AnalysisService
from truvix.modules.vehicles.dependencies import VehicleRepositoryDep
from truvix.shared.dependencies import ContainerDep, SessionDep, SettingsDep

# One engine instance serves every request: it is stateless and cheap.
_rule_based_engine = RuleBasedEngine()


def get_analysis_repository(session: SessionDep) -> AnalysisRepository:
    """Provide the analysis repository bound to the request's transaction."""
    return AnalysisRepository(session)


AnalysisRepositoryDep = Annotated[AnalysisRepository, Depends(get_analysis_repository)]


def get_analysis_service(
    analyses: AnalysisRepositoryDep,
    vehicles: VehicleRepositoryDep,
    container: ContainerDep,
    settings: SettingsDep,
) -> AnalysisService:
    """Provide the analysis workflow service for the current request."""
    return AnalysisService(
        analyses=analyses,
        vehicles=vehicles,
        storage=container.file_storage,
        engine=_rule_based_engine,
        settings=settings.storage,
    )


AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]
