from __future__ import annotations

from decimal import Decimal



def format_money(value: Decimal | float | int, currency: str = "VND") -> str:
    return f"{value:,.0f} {currency}"
