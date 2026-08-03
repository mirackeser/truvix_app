"""Single import point that populates ``Base.metadata`` with every table.

Alembic compares the live database against this metadata. A model that is not
reachable from here is invisible to autogeneration, so its table would silently
never be created; importing every model module in one place makes that class of
mistake impossible.
"""

from __future__ import annotations

from truvix.modules.auth.models import RefreshToken
from truvix.modules.users.models import SubscriptionTier, User, UserStatus
from truvix.shared.database import Base

__all__ = [
    "Base",
    "RefreshToken",
    "SubscriptionTier",
    "User",
    "UserStatus",
]
