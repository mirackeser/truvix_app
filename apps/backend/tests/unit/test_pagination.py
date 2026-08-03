"""Tests for the pagination envelope."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from truvix.shared.pagination import MAX_PAGE_SIZE, Page, PageParams


class TestPageParams:
    def test_defaults_target_the_first_page(self) -> None:
        params = PageParams()

        assert params.page == 1
        assert params.offset == 0

    def test_offset_follows_page_and_size(self) -> None:
        params = PageParams(page=4, page_size=25)

        assert params.offset == 75
        assert params.limit == 25

    def test_page_below_one_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PageParams(page=0)

    def test_page_size_above_the_ceiling_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            PageParams(page_size=MAX_PAGE_SIZE + 1)


class TestPage:
    def test_middle_page_reports_both_neighbours(self) -> None:
        page = Page[int].create(items=[4, 5, 6], total=9, params=PageParams(page=2, page_size=3))

        assert page.total_pages == 3
        assert page.has_next
        assert page.has_previous

    def test_first_page_has_no_previous(self) -> None:
        page = Page[int].create(items=[1, 2, 3], total=9, params=PageParams(page=1, page_size=3))

        assert page.has_next
        assert not page.has_previous

    def test_last_page_has_no_next(self) -> None:
        page = Page[int].create(items=[7, 8, 9], total=9, params=PageParams(page=3, page_size=3))

        assert not page.has_next
        assert page.has_previous

    def test_partial_final_page_is_counted(self) -> None:
        page = Page[int].create(items=[9], total=9, params=PageParams(page=3, page_size=4))

        assert page.total_pages == 3

    def test_empty_result_reports_no_pages(self) -> None:
        page = Page[int].create(items=[], total=0, params=PageParams())

        assert page.total_pages == 0
        assert not page.has_next
        assert not page.has_previous

    def test_computed_fields_are_serialised(self) -> None:
        page = Page[int].create(items=[1], total=5, params=PageParams(page=1, page_size=1))

        payload = page.model_dump()

        assert payload["total_pages"] == 5
        assert payload["has_next"] is True
        assert payload["has_previous"] is False
