"""Data access for user accounts.

The repository is the only place that builds queries against ``users``. Services
depend on it rather than on the session, which keeps business logic free of SQL
and makes the access patterns auditable in one file.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from truvix.modules.users.models import User


class UserRepository:
    """Reads and writes user records."""

    def __init__(self, session: AsyncSession) -> None:
        """Initialise the repository.

        Args:
            session: The session whose transaction this repository participates in.
        """
        self._session = session

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Fetch a live account by its identifier.

        Args:
            user_id: The account identifier.

        Returns:
            The account, or ``None`` when it does not exist or was deleted.
        """
        statement = select(User).where(User.id == user_id, User.deleted_at.is_(None))
        user: User | None = await self._session.scalar(statement)
        return user

    async def get_by_email(self, email: str) -> User | None:
        """Fetch a live account by its email address.

        Args:
            email: The address, already normalised to lowercase.

        Returns:
            The account, or ``None`` when no live account uses that address.
        """
        statement = select(User).where(User.email == email, User.deleted_at.is_(None))
        user: User | None = await self._session.scalar(statement)
        return user

    async def email_is_taken(self, email: str) -> bool:
        """Whether a live account already uses the given address.

        Args:
            email: The address, already normalised to lowercase.
        """
        statement = select(User.id).where(User.email == email, User.deleted_at.is_(None)).limit(1)
        return await self._session.scalar(statement) is not None

    async def phone_is_taken(self, phone_number: str) -> bool:
        """Whether a live account already uses the given phone number.

        Args:
            phone_number: The number in E.164 form.
        """
        statement = (
            select(User.id)
            .where(User.phone_number == phone_number, User.deleted_at.is_(None))
            .limit(1)
        )
        return await self._session.scalar(statement) is not None

    def add(self, user: User) -> None:
        """Stage a new account for insertion.

        The row is written when the surrounding transaction commits.

        Args:
            user: The account to persist.
        """
        self._session.add(user)

    async def flush(self) -> None:
        """Send pending changes to the database without committing.

        Needed when the caller must observe database-generated values, or
        surface a constraint violation, before the transaction ends.
        """
        await self._session.flush()
