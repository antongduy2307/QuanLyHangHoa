from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class InvoiceDTO:
    id: int
    invoice_code: str
    customer_snapshot_name: str
    total_amount: Decimal
    status: str
    invoice_datetime: datetime
