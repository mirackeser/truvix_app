"""SQLAlchemy declarative base and mixins shared by every persistence model.

The explicit constraint naming convention is what makes Alembic autogeneration
reliable: without it PostgreSQL invents constraint names, and a later migration
cannot drop a constraint whose name it does not know.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

# Deterministic constraint names, required for reversible Alembic migrations.
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def new_id() -> uuid.UUID:
    """Generate a time-ordered UUIDv7 primary key.

    Time ordering keeps newly inserted rows adjacent in the B-tree index, which
    avoids the random-write amplification that UUIDv4 primary keys cause on
    large tables.
    """
    return uuid.uuid7()


def utc_now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(UTC)


def pg_enum[EnumT: StrEnum](enum_class: type[EnumT], *, name: str) -> SQLEnum:
    """Build a native PostgreSQL enum column type from a ``StrEnum``.

    SQLAlchemy stores enum *names* by default, so ``UserStatus.ACTIVE`` would be
    written as ``ACTIVE`` while a Python-side default of ``"active"`` would be
    rejected. Storing the member values instead keeps the database labels and
    the Python values identical, which also makes raw SQL readable.

    Args:
        enum_class: The ``StrEnum`` to map.
        name: Name of the PostgreSQL type to create.
    """
    return SQLEnum(
        enum_class,
        name=name,
        native_enum=True,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class Base(DeclarativeBase):
    """Declarative base carrying the shared metadata and naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)

    # Fetch database-generated values with RETURNING during the flush that
    # writes them. Without this, a column such as ``updated_at`` is left expired
    # after an UPDATE, and reading it from a response serialiser would attempt
    # database IO from synchronous code — which fails outright under asyncio.
    # PostgreSQL supports RETURNING, so this costs no extra round trip.
    __mapper_args__ = {"eager_defaults": True}  # noqa: RUF012 - SQLAlchemy mapper contract


class UUIDPrimaryKeyMixin:
    """Adds a UUIDv7 primary key named ``id``."""

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=new_id)


class TimestampMixin:
    """Adds database-managed creation and modification timestamps.

    ``server_default`` and ``onupdate`` are set at the database level so that
    rows written outside the ORM, such as by a migration or a maintenance
    script, still carry correct timestamps.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Adds a nullable deletion timestamp for reversible removal.

    Records the user's intent to delete without destroying data that analytics,
    auditing, or an accidental-deletion recovery flow may still need.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    @property
    def is_deleted(self) -> bool:
        """Whether the row has been soft-deleted."""
        return self.deleted_at is not None
