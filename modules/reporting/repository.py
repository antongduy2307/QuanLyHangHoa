from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select

from core.enums import InvoiceLineType
from sqlalchemy.orm import Session, sessionmaker

from modules.customer.models import Customer
from modules.inventory.models import Product
from modules.reporting.dto import ReportingSummaryDTO
from modules.returns.models import ReturnInvoice, ReturnInvoiceItem
from modules.sales.models import Invoice, InvoiceItem


@dataclass(frozen=True, slots=True)
class SalesSummaryAggregate:
    gross_sales_amount: Decimal
    return_amount: Decimal
    invoice_count: int
    return_count: int


@dataclass(frozen=True, slots=True)
class ProductAggregateRow:
    product_id: int
    product_code: str
    product_name: str
    unit_type: str
    quantity: Decimal
    amount: Decimal


@dataclass(frozen=True, slots=True)
class DailyAggregateRow:
    bucket_date: str
    amount: Decimal


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

    def get_sales_summary_aggregate(self, start_datetime: datetime, end_datetime: datetime) -> SalesSummaryAggregate:
        with self._session_factory() as session:
            gross_sales_amount = session.scalar(
                select(func.coalesce(func.sum(InvoiceItem.line_total), 0))
                .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
                .where(InvoiceItem.line_type == InvoiceLineType.SALE)
                .where(Invoice.invoice_datetime >= start_datetime)
                .where(Invoice.invoice_datetime <= end_datetime)
            ) or 0
            invoice_return_amount = session.scalar(
                select(func.coalesce(func.sum(InvoiceItem.line_total), 0))
                .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
                .where(InvoiceItem.line_type == InvoiceLineType.RETURN)
                .where(Invoice.invoice_datetime >= start_datetime)
                .where(Invoice.invoice_datetime <= end_datetime)
            ) or 0
            return_amount = session.scalar(
                select(func.coalesce(func.sum(ReturnInvoiceItem.line_total), 0))
                .join(ReturnInvoice, ReturnInvoice.id == ReturnInvoiceItem.return_invoice_id)
                .where(ReturnInvoice.return_datetime >= start_datetime)
                .where(ReturnInvoice.return_datetime <= end_datetime)
            ) or 0
            invoice_count = session.scalar(
                select(func.count(Invoice.id))
                .where(Invoice.invoice_datetime >= start_datetime)
                .where(Invoice.invoice_datetime <= end_datetime)
            ) or 0
            return_count = session.scalar(
                select(func.count(ReturnInvoice.id))
                .where(ReturnInvoice.return_datetime >= start_datetime)
                .where(ReturnInvoice.return_datetime <= end_datetime)
            ) or 0
            return SalesSummaryAggregate(
                gross_sales_amount=Decimal(str(gross_sales_amount)),
                return_amount=Decimal(str(return_amount)) + Decimal(str(invoice_return_amount)),
                invoice_count=int(invoice_count),
                return_count=int(return_count),
            )

    def get_sold_product_rows(self, start_datetime: datetime, end_datetime: datetime) -> Sequence[ProductAggregateRow]:
        with self._session_factory() as session:
            statement = (
                select(
                    InvoiceItem.product_id,
                    InvoiceItem.product_code_snapshot,
                    InvoiceItem.product_name_snapshot,
                    InvoiceItem.unit_type,
                    func.coalesce(func.sum(InvoiceItem.quantity), 0),
                    func.coalesce(func.sum(InvoiceItem.line_total), 0),
                )
                .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
                .where(InvoiceItem.line_type == InvoiceLineType.SALE)
                .where(Invoice.invoice_datetime >= start_datetime)
                .where(Invoice.invoice_datetime <= end_datetime)
                .group_by(
                    InvoiceItem.product_id,
                    InvoiceItem.product_code_snapshot,
                    InvoiceItem.product_name_snapshot,
                    InvoiceItem.unit_type,
                )
            )
            rows = session.execute(statement).all()
            return [
                ProductAggregateRow(
                    product_id=int(row[0]),
                    product_code=str(row[1]),
                    product_name=str(row[2]),
                    unit_type=str(row[3].value if hasattr(row[3], "value") else row[3]),
                    quantity=Decimal(str(row[4])),
                    amount=Decimal(str(row[5])),
                )
                for row in rows
            ]

    def get_returned_product_rows(self, start_datetime: datetime, end_datetime: datetime) -> Sequence[ProductAggregateRow]:
        with self._session_factory() as session:
            statement = (
                select(
                    ReturnInvoiceItem.product_id,
                    ReturnInvoiceItem.product_code_snapshot,
                    ReturnInvoiceItem.product_name_snapshot,
                    ReturnInvoiceItem.unit_type,
                    func.coalesce(func.sum(ReturnInvoiceItem.quantity), 0),
                    func.coalesce(func.sum(ReturnInvoiceItem.line_total), 0),
                )
                .join(ReturnInvoice, ReturnInvoice.id == ReturnInvoiceItem.return_invoice_id)
                .where(ReturnInvoice.return_datetime >= start_datetime)
                .where(ReturnInvoice.return_datetime <= end_datetime)
                .group_by(
                    ReturnInvoiceItem.product_id,
                    ReturnInvoiceItem.product_code_snapshot,
                    ReturnInvoiceItem.product_name_snapshot,
                    ReturnInvoiceItem.unit_type,
                )
            )
            rows = list(session.execute(statement).all())
            invoice_return_statement = (
                select(
                    InvoiceItem.product_id,
                    InvoiceItem.product_code_snapshot,
                    InvoiceItem.product_name_snapshot,
                    InvoiceItem.unit_type,
                    func.coalesce(func.sum(InvoiceItem.quantity), 0),
                    func.coalesce(func.sum(InvoiceItem.line_total), 0),
                )
                .join(Invoice, Invoice.id == InvoiceItem.invoice_id)
                .where(InvoiceItem.line_type == InvoiceLineType.RETURN)
                .where(Invoice.invoice_datetime >= start_datetime)
                .where(Invoice.invoice_datetime <= end_datetime)
                .group_by(
                    InvoiceItem.product_id,
                    InvoiceItem.product_code_snapshot,
                    InvoiceItem.product_name_snapshot,
                    InvoiceItem.unit_type,
                )
            )
            rows.extend(session.execute(invoice_return_statement).all())
            merged: dict[tuple[int, str, str, str], list[Decimal]] = {}
            for row in rows:
                key = (int(row[0]), str(row[1]), str(row[2]), str(row[3].value if hasattr(row[3], "value") else row[3]))
                totals = merged.setdefault(key, [Decimal("0"), Decimal("0")])
                totals[0] += Decimal(str(row[4]))
                totals[1] += Decimal(str(row[5]))
            return [
                ProductAggregateRow(
                    product_id=key[0],
                    product_code=key[1],
                    product_name=key[2],
                    unit_type=key[3],
                    quantity=totals[0],
                    amount=totals[1],
                )
                for key, totals in merged.items()
            ]

    def get_daily_sales_rows(self, start_datetime: datetime, end_datetime: datetime) -> Sequence[DailyAggregateRow]:
        with self._session_factory() as session:
            statement = (
                select(func.date(Invoice.invoice_datetime), func.coalesce(func.sum(InvoiceItem.line_total), 0))
                .join(InvoiceItem, Invoice.id == InvoiceItem.invoice_id)
                .where(InvoiceItem.line_type == InvoiceLineType.SALE)
                .where(Invoice.invoice_datetime >= start_datetime)
                .where(Invoice.invoice_datetime <= end_datetime)
                .group_by(func.date(Invoice.invoice_datetime))
                .order_by(func.date(Invoice.invoice_datetime))
            )
            rows = session.execute(statement).all()
            return [DailyAggregateRow(bucket_date=str(row[0]), amount=Decimal(str(row[1]))) for row in rows]

    def get_daily_return_rows(self, start_datetime: datetime, end_datetime: datetime) -> Sequence[DailyAggregateRow]:
        with self._session_factory() as session:
            statement = (
                select(func.date(ReturnInvoice.return_datetime), func.coalesce(func.sum(ReturnInvoiceItem.line_total), 0))
                .join(ReturnInvoiceItem, ReturnInvoice.id == ReturnInvoiceItem.return_invoice_id)
                .where(ReturnInvoice.return_datetime >= start_datetime)
                .where(ReturnInvoice.return_datetime <= end_datetime)
                .group_by(func.date(ReturnInvoice.return_datetime))
                .order_by(func.date(ReturnInvoice.return_datetime))
            )
            invoice_return_statement = (
                select(func.date(Invoice.invoice_datetime), func.coalesce(func.sum(InvoiceItem.line_total), 0))
                .join(InvoiceItem, Invoice.id == InvoiceItem.invoice_id)
                .where(InvoiceItem.line_type == InvoiceLineType.RETURN)
                .where(Invoice.invoice_datetime >= start_datetime)
                .where(Invoice.invoice_datetime <= end_datetime)
                .group_by(func.date(Invoice.invoice_datetime))
            )
            merged: dict[str, Decimal] = {}
            for row in list(session.execute(statement).all()) + list(session.execute(invoice_return_statement).all()):
                bucket = str(row[0])
                merged[bucket] = merged.get(bucket, Decimal("0")) + Decimal(str(row[1]))
            return [DailyAggregateRow(bucket_date=bucket, amount=amount) for bucket, amount in sorted(merged.items())]
