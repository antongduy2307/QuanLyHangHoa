from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CustomerDTO:
    id: int
    customer_name: str
    phone: str | None
    current_balance: Decimal
    total_sales: Decimal
    is_walk_in: bool
    created_at: datetime
