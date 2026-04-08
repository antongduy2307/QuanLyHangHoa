from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReturnInvoiceDTO:
    id: int
    return_code: str
    source_invoice_id: int | None
    customer_snapshot_name: str
    is_quick_return: bool
    total_amount: Decimal
    handling_mode: str
    return_datetime: datetime
