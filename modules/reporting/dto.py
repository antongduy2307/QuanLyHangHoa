from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ReportingSummaryDTO:
    inventory_count: int
    customer_count: int
    sales_order_count: int
