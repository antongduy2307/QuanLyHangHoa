from __future__ import annotations

from core.exceptions import ValidationError



def validate_return_code(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValidationError("Ma phieu tra hang khong duoc de trong.")
    return normalized
