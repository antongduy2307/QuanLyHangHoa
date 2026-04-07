from __future__ import annotations

from core.exceptions import ValidationError



def validate_customer_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError("Ten khach hang khong duoc de trong.")
    return normalized
