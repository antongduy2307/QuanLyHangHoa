from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable


@dataclass(frozen=True, slots=True)
class CutBonusItem:
    quantity: Decimal | int | str
    quota_quantity: Decimal | int | str
    excess_unit_price: Decimal | int | str


def calculate_cut_employee_bonus(items: Iterable[CutBonusItem]) -> Decimal:
    active_items = [
        (
            _to_decimal(item.quantity),
            _to_decimal(item.quota_quantity),
            _to_decimal(item.excess_unit_price),
        )
        for item in items
        if _to_decimal(item.quantity) > 0
    ]
    if not active_items:
        return Decimal("0")

    item_count = Decimal(len(active_items))
    total_quantity = sum((quantity for quantity, _quota, _price in active_items), Decimal("0"))
    quota_avg = sum((quota for _quantity, quota, _price in active_items), Decimal("0")) / item_count
    if total_quantity <= quota_avg:
        return Decimal("0")

    reached_indices = [
        index
        for index, (quantity, quota, _price) in enumerate(active_items)
        if quantity >= quota
    ]

    if len(reached_indices) >= 2:
        quota_charged_index = min(reached_indices, key=lambda index: active_items[index][2])
        return sum(
            (
                max(Decimal("0"), quantity - quota) * price
                if index == quota_charged_index
                else quantity * price
            )
            for index, (quantity, quota, price) in enumerate(active_items)
        )

    if reached_indices:
        return sum(
            (
                max(Decimal("0"), quantity - quota) * price
                if quantity >= quota
                else quantity * price
            )
            for quantity, quota, price in active_items
        )

    return sum(
        max(Decimal("0"), quantity - (quota / item_count)) * price
        for quantity, quota, price in active_items
    )


def _to_decimal(value: Decimal | int | str) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))
