"""Dependency providers for the analysis endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends

from truvix.modules.analysis.engine import AnalysisEngine, RuleBasedEngine
from truvix.modules.analysis.llm_engine import LLMEnrichedEngine
from truvix.modules.analysis.repository import AnalysisRepository
from truvix.modules.analysis.service import AnalysisService
from truvix.modules.vehicles.dependencies import VehicleRepositoryDep
from truvix.shared.dependencies import ContainerDep, EventBusDep, SessionDep, SettingsDep

# One rule engine instance serves every request: it is stateless and cheap.
_rule_based_engine = RuleBasedEngine()


def get_analysis_engine(container: ContainerDep) -> AnalysisEngine:
    """Choose the engine for this deployment.

    With a chat model configured the report is LLM-enriched; without one the
    deterministic engine serves alone. Either way analyses always complete.
    """
    if container.chat_model is not None:
        return LLMEnrichedEngine(_rule_based_engine, container.chat_model)
    return _rule_based_engine


AnalysisEngineDep = Annotated[AnalysisEngine, Depends(get_analysis_engine)]


def get_analysis_repository(session: SessionDep) -> AnalysisRepository:
    """Provide the analysis repository bound to the request's transaction."""
    return AnalysisRepository(session)


AnalysisRepositoryDep = Annotated[AnalysisRepository, Depends(get_analysis_repository)]


def get_analysis_service(
    analyses: AnalysisRepositoryDep,
    vehicles: VehicleRepositoryDep,
    container: ContainerDep,
    settings: SettingsDep,
    engine: AnalysisEngineDep,
    events: EventBusDep,
) -> AnalysisService:
    """Provide the analysis workflow service for the current request."""
    return AnalysisService(
        analyses=analyses,
        vehicles=vehicles,
        storage=container.file_storage,
        engine=engine,
        settings=settings.storage,
        events=events,
    )


AnalysisServiceDep = Annotated[AnalysisService, Depends(get_analysis_service)]
