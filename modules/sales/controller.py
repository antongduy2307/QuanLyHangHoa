from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
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
    stock_by_unit: dict[UnitType, Decimal] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class TransactionHistoryRow:
    transaction_type: str
    transaction_id: int
    transaction_datetime: datetime
    transaction_code: str
    customer_name: str
    amount: Decimal
    display_order: int = 0
    source_ref_type: str | None = None
    source_ref_id: int | None = None
    sort_datetime: datetime | None = None


class SalesController:
    _TRANSACTION_PRIORITY = {
        "INVOICE": 2,
        "RETURN": 1,
        "DEBT_PAYMENT": 0,
    }
    _DEFAULT_DISPLAY_ORDER = {
        "INVOICE": 10,
        "RETURN": 20,
        "DEBT_PAYMENT": 30,
    }

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_customers(self, *, include_inactive: bool = False) -> Sequence[CustomerDTO]:
        service = CustomerService(CustomerRepository(self._session_factory))
        return service.list_customers(include_inactive=include_inactive)

    def list_sellable_products(self) -> list[SellableProductOption]:
        repository = InventoryRepository(self._session_factory)
        inventory_service = InventoryService(InventoryRepository(self._session_factory))
        products = repository.list_products()
        options: list[SellableProductOption] = []
        for product in products:
            enabled_prices = {
                price.unit_type: price.price
                for price in product.prices
                if price.is_enabled
            }
            if enabled_prices:
                stock_by_unit = {
                    unit_type: inventory_service.get_available_quantity(product.id, unit_type)
                    for unit_type in enabled_prices
                }
                options.append(
                    SellableProductOption(
                        product_id=product.id,
                        product_code_base=product.product_code_base,
                        product_name=product.product_name,
                        unit_mode=product.unit_mode.value,
                        enabled_prices=enabled_prices,
                        stock_by_unit=stock_by_unit,
                    )
                )
        repository.session.close()
        inventory_service._repository.session.close()
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
        invoice_datetime_by_id = {invoice.id: invoice.invoice_datetime for invoice in invoices}
        invoice_id_by_code = {invoice.invoice_code: invoice.id for invoice in invoices}
        for invoice in invoices:
            rows.append(
                TransactionHistoryRow(
                    "INVOICE",
                    invoice.id,
                    invoice.invoice_datetime,
                    invoice.invoice_code,
                    invoice.customer_snapshot_name,
                    invoice.total_amount,
                    self._DEFAULT_DISPLAY_ORDER["INVOICE"],
                    "INVOICE",
                    invoice.id,
                    invoice.invoice_datetime,
                )
            )
        for return_invoice in returns:
            customer_name = return_invoice.customer_snapshot_name
            rows.append(
                TransactionHistoryRow(
                    "RETURN",
                    return_invoice.id,
                    return_invoice.return_datetime,
                    return_invoice.return_code,
                    customer_name,
                    return_invoice.total_amount,
                    self._DEFAULT_DISPLAY_ORDER["RETURN"],
                    "RETURN",
                    return_invoice.id,
                    return_invoice.return_datetime,
                )
            )
        for ledger in debt_payments:
            source_ref_type = self._ledger_source_ref_type(ledger, invoice_id_by_code)
            source_ref_id = self._ledger_source_ref_id(ledger, invoice_id_by_code)
            rows.append(
                TransactionHistoryRow(
                    "DEBT_PAYMENT",
                    ledger.id,
                    ledger.effective_transaction_datetime,
                    str(ledger.ref_id),
                    ledger.customer.customer_name if ledger.customer else "-",
                    abs(ledger.amount_delta),
                    self._ledger_display_order(ledger),
                    source_ref_type,
                    source_ref_id,
                    self._ledger_sort_datetime(ledger, invoice_datetime_by_id, invoice_id_by_code),
                )
            )

        if transaction_type != "ALL":
            rows = [row for row in rows if row.transaction_type == transaction_type]
        if start_datetime is not None:
            rows = [row for row in rows if self._row_sort_datetime(row) >= start_datetime]
        if end_datetime is not None:
            rows = [row for row in rows if self._row_sort_datetime(row) <= end_datetime]
        if query.strip():
            needle = query.strip().lower()
            rows = [
                row for row in rows
                if needle in row.customer_name.lower()
            ]
        if sort_option == "newest":
            rows.sort(
                key=lambda row: (
                    self._row_sort_datetime(row),
                    self._row_display_order(row),
                    self._TRANSACTION_PRIORITY.get(row.transaction_type, -1),
                    row.transaction_id,
                ),
                reverse=True,
            )
        else:
            rows.sort(
                key=lambda row: (
                    self._row_sort_datetime(row),
                    self._row_display_order(row),
                    -self._TRANSACTION_PRIORITY.get(row.transaction_type, -1),
                    row.transaction_id,
                )
            )
        return rows

    def _row_display_order(self, row: TransactionHistoryRow) -> int:
        return row.display_order or self._DEFAULT_DISPLAY_ORDER.get(row.transaction_type, 100)

    @staticmethod
    def _row_sort_datetime(row: TransactionHistoryRow) -> datetime:
        return row.sort_datetime or row.transaction_datetime

    def _ledger_display_order(self, ledger: CustomerBalanceLedger) -> int:
        return ledger.display_order or self._DEFAULT_DISPLAY_ORDER["DEBT_PAYMENT"]

    def _ledger_sort_datetime(
        self,
        ledger: CustomerBalanceLedger,
        invoice_datetime_by_id: dict[int, datetime],
        invoice_id_by_code: dict[str, int],
    ) -> datetime:
        source_invoice_id = self._ledger_source_invoice_id(ledger, invoice_id_by_code)
        if source_invoice_id is not None and source_invoice_id in invoice_datetime_by_id:
            return invoice_datetime_by_id[source_invoice_id]
        return ledger.effective_transaction_datetime

    def _ledger_source_ref_type(
        self,
        ledger: CustomerBalanceLedger,
        invoice_id_by_code: dict[str, int],
    ) -> str | None:
        if ledger.source_ref_type is not None:
            return ledger.source_ref_type
        return "INVOICE" if self._ledger_source_invoice_id(ledger, invoice_id_by_code) is not None else None

    def _ledger_source_ref_id(
        self,
        ledger: CustomerBalanceLedger,
        invoice_id_by_code: dict[str, int],
    ) -> int | None:
        return ledger.source_ref_id or self._ledger_source_invoice_id(ledger, invoice_id_by_code)

    @staticmethod
    def _ledger_source_invoice_id(
        ledger: CustomerBalanceLedger,
        invoice_id_by_code: dict[str, int],
    ) -> int | None:
        if ledger.source_ref_type == "INVOICE" and ledger.source_ref_id is not None:
            return ledger.source_ref_id
        note = (ledger.note or "").strip()
        prefix = "Overpayment from invoice "
        if note.startswith(prefix):
            return invoice_id_by_code.get(note[len(prefix):].strip())
        return None

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

    def update_invoice(
        self,
        invoice_id: int,
        *,
        items: list[Mapping[str, object]],
        invoice_datetime: datetime | None = None,
        paid_amount: Decimal | None = None,
        note: str | None = None,
    ) -> object:
        service = SalesService(SalesRepository(self._session_factory))
        return service.update_invoice(
            invoice_id,
            items=items,
            invoice_datetime=invoice_datetime,
            paid_amount=paid_amount,
            note=note,
        )

    def update_invoice_datetime(self, invoice_id: int, new_datetime: datetime) -> Invoice:
        service = SalesService(SalesRepository(self._session_factory))
        return service.update_invoice_datetime(invoice_id, new_datetime)

    def delete_invoice(self, invoice_id: int) -> None:
        service = SalesService(SalesRepository(self._session_factory))
        service.delete_invoice(invoice_id)

