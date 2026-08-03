"""Single import point that populates ``Base.metadata`` with every table.

Alembic compares the live database against this metadata. A model that is not
reachable from here is invisible to autogeneration, so its table would silently
never be created; importing every model module in one place makes that class of
mistake impossible.
"""

from __future__ import annotations

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
from truvix.modules.auth.models import RefreshToken
from truvix.modules.copilot.models import CopilotConversation, CopilotMessage, MessageRole
from truvix.modules.users.models import SubscriptionTier, User, UserStatus
from truvix.modules.vehicles.models import (
    BodyType,
    Collection,
    CollectionItem,
    Currency,
    FuelType,
    ListingSource,
    PriceSnapshot,
    PriceSource,
    SellerType,
    Transmission,
    Vehicle,
)
from truvix.shared.database import Base

__all__ = [
    "AnalysisPhoto",
    "AnalysisStatus",
    "Base",
    "BodyType",
    "Collection",
    "CollectionItem",
    "CopilotConversation",
    "CopilotMessage",
    "Currency",
    "FindingCategory",
    "FindingSeverity",
    "FuelType",
    "ListingSource",
    "MessageRole",
    "PhotoKind",
    "PriceSnapshot",
    "PriceSource",
    "RefreshToken",
    "RiskFinding",
    "RiskLevel",
    "SellerType",
    "SubscriptionTier",
    "Transmission",
    "User",
    "UserStatus",
    "Vehicle",
    "VehicleAnalysis",
]
