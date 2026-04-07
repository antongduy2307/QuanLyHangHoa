from __future__ import annotations

from core.exceptions import ValidationError



def validate_product_code_base(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValidationError("Ma hang goc khong duoc de trong.")
    return normalized



def validate_product_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValidationError("Ten product khong duoc de trong.")
    return normalized
