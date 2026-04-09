from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from core.enums import PaymentMethod, UnitType
from modules.customer.dto import CustomerDTO
from modules.customer.models import CustomerBalanceLedger
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.returns.models import ReturnInvoice
from modules.returns.repository import ReturnsRepository
from modules.sales.models import Invoice
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService


@dataclass(frozen=True, slots=True)
class SellableProductOption:
    product_id: int
    product_code_base: str
    product_name: str
    unit_mode: str
    enabled_prices: dict[UnitType, Decimal]


@dataclass(frozen=True, slots=True)
class TransactionHistoryRow:
    transaction_type: str
    transaction_id: int
    transaction_datetime: datetime
    transaction_code: str
    customer_name: str
    amount: Decimal


class SalesController:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_customers(self) -> Sequence[CustomerDTO]:
        service = CustomerService(CustomerRepository(self._session_factory))
        return service.list_customers()

    def list_sellable_products(self) -> list[SellableProductOption]:
        repository = InventoryRepository(self._session_factory)
        products = repository.list_products()
        options: list[SellableProductOption] = []
        for product in products:
            enabled_prices = {
                price.unit_type: price.price
                for price in product.prices
                if price.is_enabled
            }
            if enabled_prices:
                options.append(
                    SellableProductOption(
                        product_id=product.id,
                        product_code_base=product.product_code_base,
                        product_name=product.product_name,
                        unit_mode=product.unit_mode.value,
                        enabled_prices=enabled_prices,
                    )
                )
        repository.session.close()
        return options

    def list_invoices(self) -> Sequence[Invoice]:
        repository = SalesRepository(self._session_factory)
        invoices = repository.list_invoices()
        repository.session.close()
        return invoices

    def search_invoices(self, query: str) -> Sequence[Invoice]:
        repository = SalesRepository(self._session_factory)
        invoices = repository.search_invoices_by_code(query)
        repository.session.close()
        return invoices

    def get_invoice_detail(self, invoice_id: int) -> Invoice:
        repository = SalesRepository(self._session_factory)
        invoice = repository.get_invoice(invoice_id)
        repository.session.close()
        return invoice

    def get_invoice_balance_after(self, invoice: Invoice) -> Decimal | None:
        if invoice.customer_id is None:
            return None

        repository = CustomerRepository(self._session_factory)
        session = repository.session
        service = CustomerService(repository)
        try:
            ledgers = list(service.list_reference_ledgers(invoice.customer_id, "INVOICE", invoice.id))
            if not ledgers:
                return None
            return ledgers[-1].balance_after
        finally:
            session.close()

    def list_transaction_history(
        self,
        *,
        query: str = "",
        transaction_type: str = "ALL",
        start_datetime: datetime | None = None,
        end_datetime: datetime | None = None,
        sort_option: str = "newest",
    ) -> list[TransactionHistoryRow]:
        sales_repository = SalesRepository(self._session_factory)
        returns_repository = ReturnsRepository(self._session_factory)
        customer_repository = CustomerRepository(self._session_factory)
        invoices = list(sales_repository.list_invoices())
        returns = list(returns_repository.list_return_invoices())
        debt_payments = list(customer_repository.list_debt_payments())
        sales_repository.session.close()
        returns_repository.session.close()
        customer_repository.session.close()

        rows: list[TransactionHistoryRow] = []
        for invoice in invoices:
            rows.append(TransactionHistoryRow("INVOICE", invoice.id, invoice.invoice_datetime, invoice.invoice_code, invoice.customer_snapshot_name, invoice.total_amount))
        for return_invoice in returns:
            customer_name = return_invoice.customer_snapshot_name
            rows.append(TransactionHistoryRow("RETURN", return_invoice.id, return_invoice.return_datetime, return_invoice.return_code, customer_name, return_invoice.total_amount))
        for ledger in debt_payments:
            rows.append(TransactionHistoryRow("DEBT_PAYMENT", ledger.id, ledger.created_at, str(ledger.ref_id), ledger.customer.customer_name if ledger.customer else "-", abs(ledger.amount_delta)))

        if transaction_type != "ALL":
            rows = [row for row in rows if row.transaction_type == transaction_type]
        if start_datetime is not None:
            rows = [row for row in rows if row.transaction_datetime >= start_datetime]
        if end_datetime is not None:
            rows = [row for row in rows if row.transaction_datetime <= end_datetime]
        if query.strip():
            needle = query.strip().lower()
            rows = [
                row for row in rows
                if needle in row.customer_name.lower() or needle in row.transaction_code.lower()
            ]
        rows.sort(key=lambda row: row.transaction_datetime, reverse=(sort_option == "newest"))
        return rows

    def create_invoice(
        self,
        *,
        customer_id: int | None,
        customer_snapshot_name: str,
        invoice_datetime: datetime,
        items: list[Mapping[str, object]],
        paid_amount: Decimal,
        payment_method: PaymentMethod | None,
        note: str | None = None,
    ) -> object:
        service = SalesService(SalesRepository(self._session_factory))
        return service.create_invoice(
            customer_id=customer_id,
            customer_snapshot_name=customer_snapshot_name,
            invoice_datetime=invoice_datetime,
            items=items,
            paid_amount=paid_amount,
            payment_method=payment_method,
            note=note,
        )

    def update_invoice(self, invoice_id: int, *, items: list[Mapping[str, object]], note: str | None = None) -> object:
        service = SalesService(SalesRepository(self._session_factory))
        return service.update_invoice(invoice_id, items=items, note=note)

    def delete_invoice(self, invoice_id: int) -> None:
        service = SalesService(SalesRepository(self._session_factory))
        service.delete_invoice(invoice_id)

