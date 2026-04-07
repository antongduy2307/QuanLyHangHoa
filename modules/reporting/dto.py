from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class ReportingSummaryDTO:
    inventory_count: int
    customer_count: int
    sales_order_count: int


@dataclass(frozen=True, slots=True)
class SalesSummaryDTO:
    start_datetime: datetime
    end_datetime: datetime
    gross_sales_amount: Decimal
    return_amount: Decimal
    net_revenue: Decimal
    invoice_count: int
    return_count: int


@dataclass(frozen=True, slots=True)
class TopProductReportRowDTO:
    product_id: int
    product_code: str
    product_name: str
    unit_type: str
    sold_quantity: Decimal
    gross_revenue: Decimal
    returned_quantity: Decimal
    return_amount: Decimal
    net_quantity: Decimal
    net_revenue: Decimal


@dataclass(frozen=True, slots=True)
class RevenueTimeseriesPointDTO:
    bucket_date: date
    gross_sales_amount: Decimal
    return_amount: Decimal
    net_revenue: Decimal


@dataclass(frozen=True, slots=True)
class DateRangePresetDTO:
    start_datetime: datetime
    end_datetime: datetime
