"""SQLAlchemy declarative base and mixins shared by every persistence model.

The explicit constraint naming convention is what makes Alembic autogeneration
reliable: without it PostgreSQL invents constraint names, and a later migration
cannot drop a constraint whose name it does not know.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, func
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


class Base(DeclarativeBase):
    """Declarative base carrying the shared metadata and naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


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
