"""Tests for Turkish number and price formatting."""

from __future__ import annotations

from decimal import Decimal

import pytest

from truvix.shared.formatting import format_number, format_price


class TestFormatNumber:
    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (0, "0"),
            (999, "999"),
            (1000, "1.000"),
            (25_000, "25.000"),
            (1_250_000, "1.250.000"),
            (-25_000, "-25.000"),
        ],
        ids=["zero", "below_grouping", "one_thousand", "typical_drop", "price", "negative"],
    )
    def test_groups_with_full_stops(self, value: int, expected: str) -> None:
        assert format_number(value) == expected

    def test_decimals_use_a_comma(self) -> None:
        assert format_number(Decimal("1234567.89"), decimals=2) == "1.234.567,89"

    def test_decimals_are_rounded_not_truncated(self) -> None:
        assert format_number(Decimal("0.567"), decimals=2) == "0,57"

    def test_a_float_average_renders_without_decimals(self) -> None:
        # Annual mileage arrives as a float from a division.
        assert format_number(33_333.333) == "33.333"


class TestFormatPrice:
    def test_appends_the_currency(self) -> None:
        assert format_price(Decimal("1250000.00"), "TRY") == "1.250.000 TRY"

    def test_never_uses_english_separators(self) -> None:
        rendered = format_price(Decimal("1250000.00"), "TRY")

        assert "," not in rendered
