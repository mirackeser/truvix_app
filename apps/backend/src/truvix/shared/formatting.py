"""Locale-aware formatting for user-facing text.

Truvix writes to Turkish users, whose number convention is the inverse of the
English one: groups are separated by a full stop and decimals by a comma. A
price rendered as "25,000 TL" reads as twenty-five to a Turkish speaker, so
every figure that reaches a notification, report or chat message goes through
here rather than through a bare format specifier.

The standard library's ``locale`` module is deliberately avoided: it mutates
process-global state and depends on locales being installed on the host, which
makes output differ between a developer's laptop and a container.
"""

from __future__ import annotations

from decimal import Decimal

# English grouping first, then transposed; doing it in one pass would need a
# placeholder to avoid the two separators overwriting each other.
_SEPARATOR_SWAP = str.maketrans({",": ".", ".": ","})


def format_number(value: Decimal | int | float, *, decimals: int = 0) -> str:
    """Render a number with Turkish separators.

    Args:
        value: The number to render.
        decimals: How many decimal places to keep.

    Returns:
        The number with "." between thousands and "," before decimals, for
        example ``25.000`` or ``1.234.567,89``.
    """
    return f"{value:,.{decimals}f}".translate(_SEPARATOR_SWAP)


def format_price(value: Decimal, currency: str) -> str:
    """Render a price with its currency, as the app displays it.

    Args:
        value: The amount.
        currency: ISO 4217 code, such as ``"TRY"``.

    Returns:
        The amount followed by the currency, for example ``1.250.000 TRY``.
    """
    return f"{format_number(value)} {currency}"
