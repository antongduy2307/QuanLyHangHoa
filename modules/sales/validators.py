from __future__ import annotations

from core.exceptions import ValidationError



def validate_invoice_code(value: str) -> str:
    normalized = value.strip().upper()
    if not normalized:
        raise ValidationError("Ma hoa don khong duoc de trong.")
    return normalized
