"""Generic pagination primitives shared by every list endpoint.

A single page envelope across the API means the mobile client implements
infinite scrolling once and reuses it for the garage, notifications and analysis
history screens.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Annotated, Self

from pydantic import BaseModel, Field, computed_field

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class PageParams(BaseModel):
    """Query parameters controlling offset-based pagination."""

    page: Annotated[int, Field(ge=1, description="One-based page number.")] = 1
    page_size: Annotated[
        int,
        Field(
            ge=1,
            le=MAX_PAGE_SIZE,
            description=f"Items per page, at most {MAX_PAGE_SIZE}.",
        ),
    ] = DEFAULT_PAGE_SIZE

    @property
    def offset(self) -> int:
        """Number of rows to skip in the underlying query."""
        return (self.page - 1) * self.page_size

    @property
    def limit(self) -> int:
        """Maximum number of rows the underlying query may return."""
        return self.page_size


class Page[ItemT](BaseModel):
    """A single page of results together with its navigation metadata."""

    items: Sequence[ItemT]
    total: Annotated[int, Field(ge=0, description="Total items matching the query.")]
    page: Annotated[int, Field(ge=1)]
    page_size: Annotated[int, Field(ge=1)]

    @computed_field  # type: ignore[prop-decorator]
    @property
    def total_pages(self) -> int:
        """Number of pages available for the current page size."""
        if self.total == 0:
            return 0
        return -(-self.total // self.page_size)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_next(self) -> bool:
        """Whether a further page exists after this one."""
        return self.page < self.total_pages

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_previous(self) -> bool:
        """Whether a page exists before this one."""
        return self.page > 1

    @classmethod
    def create(cls, *, items: Sequence[ItemT], total: int, params: PageParams) -> Self:
        """Build a page from a query result and the parameters that produced it.

        Args:
            items: The rows belonging to the requested page.
            total: Total number of rows matching the query, ignoring pagination.
            params: The pagination parameters the query was executed with.
        """
        return cls(items=items, total=total, page=params.page, page_size=params.page_size)
