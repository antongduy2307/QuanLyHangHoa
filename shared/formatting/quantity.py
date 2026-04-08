from __future__ import annotations

from decimal import Decimal


def format_quantity(value: Decimal | int | str | object) -> str:
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    if decimal_value == decimal_value.to_integral_value():
        return str(int(decimal_value))
    normalized = decimal_value.normalize()
    return format(normalized, 'f').rstrip('0').rstrip('.') or '0'
