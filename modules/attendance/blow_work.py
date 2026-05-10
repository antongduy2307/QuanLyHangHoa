from __future__ import annotations

from decimal import Decimal

from modules.attendance.models import WorkInputType


BLOW_QUANTITY_WORK_QUOTA = 3


def calculate_blow_work_amount(input_type: WorkInputType, quantity: int, unit_price: int | Decimal) -> int:
    if input_type == WorkInputType.TICK:
        return int(unit_price) if quantity > 0 else 0
    if input_type == WorkInputType.QUANTITY:
        return max(0, quantity - BLOW_QUANTITY_WORK_QUOTA) * int(unit_price)
    return 0
