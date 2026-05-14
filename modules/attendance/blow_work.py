from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from modules.attendance.models import WorkInputType


BLOW_QUANTITY_WORK_QUOTA = Decimal("3")
BLOW_QUANTITY_QUOTA_WORK_NAME = "Thừa máy"


def is_blow_quantity_quota_work(work_type_name: str | None) -> bool:
    return (work_type_name or "").strip() == BLOW_QUANTITY_QUOTA_WORK_NAME


def calculate_blow_work_amount(
    input_type: WorkInputType,
    quantity: Decimal | int | str,
    unit_price: int | Decimal,
    work_type_name: str | None = None,
) -> int:
    quantity_value = _to_decimal(quantity)
    unit_price_value = _to_decimal(unit_price)
    if input_type == WorkInputType.TICK:
        return int(unit_price_value) if quantity_value > 0 else 0
    if input_type == WorkInputType.QUANTITY:
        if is_blow_quantity_quota_work(work_type_name):
            return _money_to_int(max(Decimal("0"), quantity_value - BLOW_QUANTITY_WORK_QUOTA) * unit_price_value)
        return _money_to_int(quantity_value * unit_price_value)
    return 0


def _to_decimal(value: Decimal | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _money_to_int(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
