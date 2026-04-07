from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from modules.customer.service import CustomerService
from modules.customer.repository import CustomerRepository
from modules.returns.repository import ReturnsRepository
from modules.returns.service import ReturnService
from modules.sales.models import Invoice
from modules.sales.repository import SalesRepository


@dataclass(frozen=True, slots=True)
class SourceInvoiceSearchRow:
    invoice_id: int
    invoice_code: str
    customer_label: str
    invoice_datetime: datetime


@dataclass(frozen=True, slots=True)
class SourceInvoiceItemRow:
    source_invoice_item_id: int
    product_code_snapshot: str
    product_name_snapshot: str
    unit_type: str
    purchased_quantity: Decimal
    already_returned_quantity: Decimal
    remaining_returnable_quantity: Decimal
    unit_price: Decimal


@dataclass(frozen=True, slots=True)
class SourceInvoiceDetail:
    invoice_id: int
    invoice_code: str
    invoice_datetime: datetime
    customer_name: str
    customer_id: int | None
    current_balance: Decimal | None
    items: tuple[SourceInvoiceItemRow, ...]


class ReturnController:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def search_source_invoices(self, query: str) -> Sequence[SourceInvoiceSearchRow]:
        repository = SalesRepository(self._session_factory)
        invoices = repository.search_invoices_by_code(query)
        repository.session.close()
        return [
            SourceInvoiceSearchRow(
                invoice_id=invoice.id,
                invoice_code=invoice.invoice_code,
                customer_label=invoice.customer_snapshot_name,
                invoice_datetime=invoice.invoice_datetime,
            )
            for invoice in invoices
        ]

    def load_source_invoice_details(self, invoice_id: int) -> SourceInvoiceDetail:
        sales_repository = SalesRepository(self._session_factory)
        returns_repository = ReturnsRepository(self._session_factory)
        customer_service = CustomerService(CustomerRepository(self._session_factory))

        invoice = sales_repository.get_invoice(invoice_id)
        current_balance = None
        if invoice.customer_id is not None:
            current_balance = customer_service.get_customer(invoice.customer_id).current_balance

        item_rows: list[SourceInvoiceItemRow] = []
        for item in invoice.items:
            already_returned = returns_repository.get_total_returned_quantity(item.id)
            item_rows.append(
                SourceInvoiceItemRow(
                    source_invoice_item_id=item.id,
                    product_code_snapshot=item.product_code_snapshot,
                    product_name_snapshot=item.product_name_snapshot,
                    unit_type=item.unit_type.value,
                    purchased_quantity=item.quantity,
                    already_returned_quantity=already_returned,
                    remaining_returnable_quantity=item.quantity - already_returned,
                    unit_price=item.unit_price,
                )
            )

        sales_repository.session.close()
        returns_repository.session.close()
        return SourceInvoiceDetail(
            invoice_id=invoice.id,
            invoice_code=invoice.invoice_code,
            invoice_datetime=invoice.invoice_datetime,
            customer_name=invoice.customer_snapshot_name,
            customer_id=invoice.customer_id,
            current_balance=current_balance,
            items=tuple(item_rows),
        )

    def create_return_invoice(
        self,
        *,
        source_invoice_id: int,
        return_datetime: datetime,
        items: list[Mapping[str, object]],
        handling_mode: str,
        note: str | None = None,
    ) -> object:
        service = ReturnService(ReturnsRepository(self._session_factory), sales_repository=SalesRepository(self._session_factory))
        return service.create_return_invoice(
            source_invoice_id=source_invoice_id,
            return_datetime=return_datetime,
            items=items,
            handling_mode=handling_mode,
            note=note,
        )
