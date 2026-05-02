from __future__ import annotations

from decimal import Decimal


def format_money(value: Decimal | float | int, currency: str = "VND") -> str:
    return f"{value:,.0f} {currency}"


def format_money_precise(value: Decimal | float | int, currency: str = "VND") -> str:
    amount = value if isinstance(value, Decimal) else Decimal(str(value))
    normalized = amount.quantize(Decimal("0.01"))
    text = f"{normalized:,.2f}".rstrip("0").rstrip(".")
    return f"{text} {currency}"
