from __future__ import annotations

from decimal import Decimal

from modules.attendance.models import WorkInputType


BLOW_QUANTITY_WORK_QUOTA = 3
BLOW_QUANTITY_QUOTA_WORK_NAME = "Thừa máy"


def is_blow_quantity_quota_work(work_type_name: str | None) -> bool:
    return (work_type_name or "").strip() == BLOW_QUANTITY_QUOTA_WORK_NAME


def calculate_blow_work_amount(
    input_type: WorkInputType,
    quantity: int,
    unit_price: int | Decimal,
    work_type_name: str | None = None,
) -> int:
    if input_type == WorkInputType.TICK:
        return int(unit_price) if quantity > 0 else 0
    if input_type == WorkInputType.QUANTITY:
        if is_blow_quantity_quota_work(work_type_name):
            return max(0, quantity - BLOW_QUANTITY_WORK_QUOTA) * int(unit_price)
        return quantity * int(unit_price)
    return 0
