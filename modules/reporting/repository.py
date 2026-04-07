from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from modules.customer.models import Customer
from modules.inventory.models import Product
from modules.reporting.dto import ReportingSummaryDTO
from modules.sales.models import Invoice


class ReportingRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get_summary(self) -> ReportingSummaryDTO:
        with self._session_factory() as session:
            product_count = session.scalar(select(func.count()).select_from(Product)) or 0
            customer_count = session.scalar(select(func.count()).select_from(Customer)) or 0
            invoice_count = session.scalar(select(func.count()).select_from(Invoice)) or 0
            return ReportingSummaryDTO(
                inventory_count=int(product_count),
                customer_count=int(customer_count),
                sales_order_count=int(invoice_count),
            )
