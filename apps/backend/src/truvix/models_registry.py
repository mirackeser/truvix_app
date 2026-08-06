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
from truvix.modules.auth.models import EmailVerificationToken, RefreshToken
from truvix.modules.copilot.models import CopilotConversation, CopilotMessage, MessageRole
from truvix.modules.notifications.models import (
    Notification,
    NotificationCategory,
    NotificationPreference,
)
from truvix.modules.subscriptions.models import (
    Entitlement,
    EntitlementStatus,
    StoreEnvironment,
)
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
    "EmailVerificationToken",
    "Entitlement",
    "EntitlementStatus",
    "FindingCategory",
    "FindingSeverity",
    "FuelType",
    "ListingSource",
    "MessageRole",
    "Notification",
    "NotificationCategory",
    "NotificationPreference",
    "PhotoKind",
    "PriceSnapshot",
    "PriceSource",
    "RefreshToken",
    "RiskFinding",
    "RiskLevel",
    "SellerType",
    "StoreEnvironment",
    "SubscriptionTier",
    "Transmission",
    "User",
    "UserStatus",
    "Vehicle",
    "VehicleAnalysis",
]
