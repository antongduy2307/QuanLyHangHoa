from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from core.exceptions import ValidationError
from modules.customer.dto import CustomerDTO
from modules.customer.mappers import to_dto
from modules.customer.models import CustomerBalanceLedger
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.returns.models import ReturnInvoice
from modules.returns.repository import ReturnsRepository
from modules.sales.models import Invoice
from modules.sales.repository import SalesRepository


@dataclass(frozen=True, slots=True)
class CustomerHistoryEntry:
    transaction_id: int
    transaction_kind: str
    transaction_datetime: datetime
    transaction_type: str
    item_summary: str
    amount: Decimal
    display_order: int = 0
    source_ref_type: str | None = None
    source_ref_id: int | None = None
    sort_datetime: datetime | None = None


@dataclass(frozen=True, slots=True)
class CustomerDebtEntry:
    transaction_id: int
    transaction_kind: str
    transaction_datetime: datetime
    transaction_type: str
    amount: Decimal
    balance_after: Decimal
    display_order: int = 0
    source_ref_type: str | None = None
    source_ref_id: int | None = None
    sort_datetime: datetime | None = None


@dataclass(frozen=True, slots=True)
class CustomerDetailData:
    customer: CustomerDTO
    recent_history: tuple[CustomerHistoryEntry, ...]


class CustomerController:
    _TRANSACTION_PRIORITY = {
        "INVOICE": 2,
        "RETURN": 1,
        "DEBT_PAYMENT": 0,
    }
    _DEFAULT_DISPLAY_ORDER = {
        "OPENING_BALANCE": 0,
        "BALANCE_ADJUSTMENT": 5,
        "INVOICE": 10,
        "RETURN": 20,
        "DEBT_PAYMENT": 30,
    }
    VALID_SORTS = {
        "name_asc",
        "name_desc",
        "balance_asc",
        "balance_desc",
        "sales_asc",
        "sales_desc",
    }

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_customers(self, sort_option: str = "name_asc", only_positive_debt: bool = False) -> list[CustomerDTO]:
        customers = self._load_customers()
        customers = self._apply_debt_filter(customers, only_positive_debt)
        return self._sort_customers(customers, sort_option)

    def search_customers(self, query: str, sort_option: str = "name_asc", only_positive_debt: bool = False) -> list[CustomerDTO]:
        customers = self._load_customers()
        needle = query.strip().lower()
        if needle:
            customers = [customer for customer in customers if needle in customer.customer_name.lower()]
        customers = self._apply_debt_filter(customers, only_positive_debt)
        return self._sort_customers(customers, sort_option)

    def create_customer(
        self,
        *,
        customer_name: str,
        phone: str | None,
        address: str | None,
        note: str | None,
        initial_balance: Decimal,
    ) -> CustomerDTO:
        service = CustomerService(CustomerRepository(self._session_factory))
        customer = service.create_customer(
            customer_name=customer_name,
            phone=phone,
            address=address,
            note=note,
            initial_balance=initial_balance,
        )
        dto = to_dto(customer)
        service._repository.session.close()
        return dto

    def delete_customer(self, customer_id: int) -> None:
        service = CustomerService(CustomerRepository(self._session_factory))
        service.delete_customer(customer_id)
        service._repository.session.close()

    def update_customer(
        self,
        customer_id: int,
        *,
        customer_name: str,
        phone: str | None,
        address: str | None,
        note: str | None,
        current_balance: Decimal,
    ) -> CustomerDTO:
        service = CustomerService(CustomerRepository(self._session_factory))
        customer = service.update_customer(
            customer_id,
            customer_name=customer_name,
            phone=phone,
            address=address,
            note=note,
            target_balance=current_balance,
        )
        dto = to_dto(customer)
        service._repository.session.close()
        return dto

    def pay_debt(
        self,
        customer_id: int,
        amount: Decimal,
        note: str | None = None,
        payment_datetime: datetime | None = None,
    ) -> object:
        service = CustomerService(CustomerRepository(self._session_factory))
        return service.pay_debt(customer_id, amount, note=note, payment_datetime=payment_datetime)

    def update_debt_payment(
        self,
        ledger_id: int,
        amount: Decimal,
        note: str | None = None,
        payment_datetime: datetime | None = None,
    ) -> CustomerBalanceLedger:
        service = CustomerService(CustomerRepository(self._session_factory))
        ledger = service.update_debt_payment(ledger_id, amount, note=note, payment_datetime=payment_datetime)
        service._repository.session.close()
        return ledger

    def list_debt_payments(self) -> Sequence[CustomerBalanceLedger]:
        repository = CustomerRepository(self._session_factory)
        entries = repository.list_debt_payments()
        repository.session.close()
        return entries

    def search_debt_payments(self, query: str) -> Sequence[CustomerBalanceLedger]:
        repository = CustomerRepository(self._session_factory)
        entries = repository.search_debt_payments(query)
        repository.session.close()
        return entries

    def get_debt_payment_detail(self, ledger_id: int) -> CustomerBalanceLedger:
        repository = CustomerRepository(self._session_factory)
        ledger = repository.get_ledger(ledger_id)
        repository.session.close()
        return ledger

    def update_debt_payment_datetime(self, ledger_id: int, new_datetime: datetime) -> CustomerBalanceLedger:
        service = CustomerService(CustomerRepository(self._session_factory))
        ledger = service.update_debt_payment_datetime(ledger_id, new_datetime)
        service._repository.session.close()
        return ledger

    def delete_debt_payment(self, ledger_id: int) -> None:
        service = CustomerService(CustomerRepository(self._session_factory))
        service.delete_debt_payment(ledger_id)
        service._repository.session.close()

    def get_customer_with_recent_history(self, customer_id: int, limit: int = 3) -> CustomerDetailData:
        customer_repository = CustomerRepository(self._session_factory)
        sales_repository = SalesRepository(self._session_factory)
        returns_repository = ReturnsRepository(self._session_factory)
        customer = customer_repository.get_customer(customer_id)
        invoices = tuple(sales_repository.get_recent_invoices_by_customer(customer_id, limit=limit))
        return_invoices = tuple(returns_repository.get_recent_return_invoices_by_customer(customer_id, limit=limit))
        debt_payments = tuple(customer_repository.get_recent_debt_payments_by_customer(customer_id, limit=limit))
        customer_repository.session.close()
        sales_repository.session.close()
        returns_repository.session.close()
        history = self._merge_recent_history(invoices, return_invoices, debt_payments, limit=limit)
        return CustomerDetailData(customer=to_dto(customer), recent_history=history)

    def get_customer_with_recent_invoices(self, customer_id: int, limit: int = 3) -> CustomerDetailData:
        return self.get_customer_with_recent_history(customer_id, limit=limit)

    def list_customer_trade_history(self, customer_id: int) -> tuple[CustomerHistoryEntry, ...]:
        sales_repository = SalesRepository(self._session_factory)
        returns_repository = ReturnsRepository(self._session_factory)
        invoices = tuple(sales_repository.list_invoices_by_customer(customer_id))
        return_invoices = tuple(returns_repository.list_return_invoices_by_customer(customer_id))
        sales_repository.session.close()
        returns_repository.session.close()

        entries: list[CustomerHistoryEntry] = []
        entries.extend(
            CustomerHistoryEntry(
                transaction_id=invoice.id,
                transaction_kind="INVOICE",
                transaction_datetime=invoice.invoice_datetime,
                transaction_type="Bán hàng",
                item_summary=self._join_item_names(invoice.items),
                amount=invoice.total_amount,
                display_order=self._DEFAULT_DISPLAY_ORDER["INVOICE"],
                source_ref_type="INVOICE",
                source_ref_id=invoice.id,
                sort_datetime=invoice.invoice_datetime,
            )
            for invoice in invoices
        )
        entries.extend(
            CustomerHistoryEntry(
                transaction_id=return_invoice.id,
                transaction_kind="RETURN",
                transaction_datetime=return_invoice.return_datetime,
                transaction_type="Trả hàng",
                item_summary=self._join_item_names(return_invoice.items),
                amount=return_invoice.total_amount,
                display_order=self._DEFAULT_DISPLAY_ORDER["RETURN"],
                source_ref_type="RETURN",
                source_ref_id=return_invoice.id,
                sort_datetime=return_invoice.return_datetime,
            )
            for return_invoice in return_invoices
        )
        self._sort_history_entries(entries)
        return tuple(entries)

    def list_customer_debt_history(self, customer_id: int) -> tuple[CustomerDebtEntry, ...]:
        sales_repository = SalesRepository(self._session_factory)
        returns_repository = ReturnsRepository(self._session_factory)
        customer_repository = CustomerRepository(self._session_factory)

        invoices = tuple(sales_repository.list_invoices_by_customer(customer_id))
        return_invoices = tuple(returns_repository.list_return_invoices_by_customer(customer_id))
        debt_payments = tuple(customer_repository.list_debt_payments_by_customer(customer_id))
        ledgers = tuple(customer_repository.list_balance_ledgers_by_customer(customer_id))
        sales_repository.session.close()
        returns_repository.session.close()
        customer_repository.session.close()

        invoice_ledgers = self._group_ledgers_by_ref(ledgers, "INVOICE")
        return_ledgers = self._group_ledgers_by_ref(ledgers, "RETURN")
        invoice_id_by_code = {invoice.invoice_code: invoice.id for invoice in invoices}
        invoice_balances = {ref_id: entries[-1].balance_after for ref_id, entries in invoice_ledgers.items()}
        return_balances = {ref_id: entries[-1].balance_after for ref_id, entries in return_ledgers.items()}
        invoice_timeline_datetimes = {
            ref_id: self._reference_effective_datetime(entries)
            for ref_id, entries in invoice_ledgers.items()
        }
        return_timeline_datetimes = {
            ref_id: self._reference_effective_datetime(entries)
            for ref_id, entries in return_ledgers.items()
        }

        entries: list[CustomerDebtEntry] = []
        entries.extend(
            CustomerDebtEntry(
                transaction_id=ledger.id,
                transaction_kind=ledger.event_type,
                transaction_datetime=ledger.effective_transaction_datetime,
                transaction_type=self._debt_ledger_label(ledger),
                amount=ledger.amount_delta,
                balance_after=ledger.balance_after,
                display_order=self._DEFAULT_DISPLAY_ORDER.get(ledger.event_type, 0),
                source_ref_type=ledger.source_ref_type,
                source_ref_id=ledger.source_ref_id,
                sort_datetime=ledger.effective_transaction_datetime,
            )
            for ledger in ledgers
            if ledger.event_type in {"OPENING_BALANCE", "BALANCE_ADJUSTMENT", "ADJUSTMENT", "MANUAL", "CUSTOMER_BALANCE_ADJUSTMENT", "INITIAL_DEBT"}
            and (ledger.ref_type or "").upper() not in {"INVOICE", "RETURN", "DEBT_PAYMENT"}
        )
        entries.extend(
            CustomerDebtEntry(
                transaction_id=invoice.id,
                transaction_kind="INVOICE",
                transaction_datetime=invoice_timeline_datetimes[invoice.id],
                transaction_type="Bán hàng",
                amount=invoice.total_amount,
                balance_after=invoice_balances[invoice.id],
                display_order=self._DEFAULT_DISPLAY_ORDER["INVOICE"],
                source_ref_type="INVOICE",
                source_ref_id=invoice.id,
                sort_datetime=invoice_timeline_datetimes[invoice.id],
            )
            for invoice in invoices
            if invoice.id in invoice_balances and invoice.id in invoice_timeline_datetimes
        )
        entries.extend(
            CustomerDebtEntry(
                transaction_id=return_invoice.id,
                transaction_kind="RETURN",
                transaction_datetime=return_timeline_datetimes[return_invoice.id],
                transaction_type="Trả hàng",
                amount=return_invoice.total_amount,
                balance_after=return_balances[return_invoice.id],
                display_order=self._DEFAULT_DISPLAY_ORDER["RETURN"],
                source_ref_type="RETURN",
                source_ref_id=return_invoice.id,
                sort_datetime=return_timeline_datetimes[return_invoice.id],
            )
            for return_invoice in return_invoices
            if return_invoice.id in return_balances and return_invoice.id in return_timeline_datetimes
        )
        entries.extend(
            CustomerDebtEntry(
                transaction_id=ledger.id,
                transaction_kind="DEBT_PAYMENT",
                transaction_datetime=ledger.effective_transaction_datetime,
                transaction_type="Trả nợ",
                amount=abs(ledger.amount_delta),
                balance_after=ledger.balance_after,
                display_order=self._ledger_display_order(ledger),
                source_ref_type=self._ledger_source_ref_type(ledger, invoice_id_by_code),
                source_ref_id=self._ledger_source_ref_id(ledger, invoice_id_by_code),
                sort_datetime=ledger.effective_transaction_datetime,
            )
            for ledger in debt_payments
        )
        self._sort_debt_history_entries(entries)
        return tuple(entries)

    def is_phone_duplicate(self, phone: str, *, excluding_customer_id: int | None = None) -> bool:
        normalized_phone = phone.strip()
        if not normalized_phone:
            return False
        repository = CustomerRepository(self._session_factory)
        customers = repository.list_customers()
        repository.session.close()
        for customer in customers:
            if customer.phone == normalized_phone and customer.id != excluding_customer_id:
                return True
        return False

    def _load_customers(self) -> list[CustomerDTO]:
        repository = CustomerRepository(self._session_factory)
        customers = repository.list_customers()
        repository.session.close()
        return [to_dto(customer) for customer in customers]

    def _apply_debt_filter(self, customers: list[CustomerDTO], only_positive_debt: bool) -> list[CustomerDTO]:
        if not only_positive_debt:
            return customers
        return [
            customer
            for customer in customers
            if (customer.current_balance or Decimal("0")) > Decimal("0")
        ]

    def _sort_customers(self, customers: list[CustomerDTO], sort_option: str) -> list[CustomerDTO]:
        if sort_option not in self.VALID_SORTS:
            raise ValidationError("sort_option không hợp lệ.")

        sorted_customers = list(customers)
        if sort_option == "name_asc":
            sorted_customers.sort(key=lambda customer: customer.customer_name.lower())
        elif sort_option == "name_desc":
            sorted_customers.sort(key=lambda customer: customer.customer_name.lower(), reverse=True)
        elif sort_option == "balance_asc":
            sorted_customers.sort(key=lambda customer: customer.current_balance)
        elif sort_option == "balance_desc":
            sorted_customers.sort(key=lambda customer: customer.current_balance, reverse=True)
        elif sort_option == "sales_asc":
            sorted_customers.sort(key=lambda customer: customer.total_sales)
        elif sort_option == "sales_desc":
            sorted_customers.sort(key=lambda customer: customer.total_sales, reverse=True)
        return sorted_customers

    def _merge_recent_history(
        self,
        invoices: Sequence[Invoice],
        return_invoices: Sequence[ReturnInvoice],
        debt_payments: Sequence[CustomerBalanceLedger],
        *,
        limit: int,
    ) -> tuple[CustomerHistoryEntry, ...]:
        entries: list[CustomerHistoryEntry] = []
        invoice_datetime_by_id = {invoice.id: invoice.invoice_datetime for invoice in invoices}
        invoice_id_by_code = {invoice.invoice_code: invoice.id for invoice in invoices}
        entries.extend(
            CustomerHistoryEntry(
                transaction_id=invoice.id,
                transaction_kind="INVOICE",
                transaction_datetime=invoice.invoice_datetime,
                transaction_type="Bán hàng",
                item_summary=self._join_item_names(invoice.items),
                amount=invoice.total_amount,
                display_order=self._DEFAULT_DISPLAY_ORDER["INVOICE"],
                source_ref_type="INVOICE",
                source_ref_id=invoice.id,
                sort_datetime=invoice.invoice_datetime,
            )
            for invoice in invoices
        )
        entries.extend(
            CustomerHistoryEntry(
                transaction_id=return_invoice.id,
                transaction_kind="RETURN",
                transaction_datetime=return_invoice.return_datetime,
                transaction_type="Trả hàng",
                item_summary=self._join_item_names(return_invoice.items),
                amount=return_invoice.total_amount,
                display_order=self._DEFAULT_DISPLAY_ORDER["RETURN"],
                source_ref_type="RETURN",
                source_ref_id=return_invoice.id,
                sort_datetime=return_invoice.return_datetime,
            )
            for return_invoice in return_invoices
        )
        entries.extend(
            CustomerHistoryEntry(
                transaction_id=ledger.id,
                transaction_kind="DEBT_PAYMENT",
                transaction_datetime=ledger.effective_transaction_datetime,
                transaction_type="Trả nợ",
                item_summary="-",
                amount=abs(ledger.amount_delta),
                display_order=self._ledger_display_order(ledger),
                source_ref_type=self._ledger_source_ref_type(ledger, invoice_id_by_code),
                source_ref_id=self._ledger_source_ref_id(ledger, invoice_id_by_code),
                sort_datetime=self._ledger_sort_datetime(ledger, invoice_datetime_by_id, invoice_id_by_code),
            )
            for ledger in debt_payments
        )
        self._sort_history_entries(entries)
        return tuple(entries[:limit])

    @staticmethod
    def _join_item_names(items: Sequence[object]) -> str:
        names: list[str] = []
        seen: set[str] = set()
        for item in items:
            product_name = getattr(item, "product_name_snapshot", "").strip()
            if not product_name or product_name in seen:
                continue
            seen.add(product_name)
            names.append(product_name)
        return ", ".join(names) if names else "-"

    @staticmethod
    def _group_ledgers_by_ref(
        ledgers: Sequence[CustomerBalanceLedger],
        ref_type: str,
    ) -> dict[int, list[CustomerBalanceLedger]]:
        grouped: dict[int, list[CustomerBalanceLedger]] = {}
        for ledger in ledgers:
            if ledger.ref_type != ref_type:
                continue
            grouped.setdefault(ledger.ref_id, []).append(ledger)
        return grouped

    def _sort_history_entries(self, entries: list[CustomerHistoryEntry | CustomerDebtEntry]) -> None:
        entries.sort(
            key=lambda entry: (
                self._entry_sort_datetime(entry),
                self._entry_display_order(entry),
                self._TRANSACTION_PRIORITY.get(entry.transaction_kind, -1),
                entry.transaction_id,
            ),
            reverse=True,
        )

    def _sort_debt_history_entries(self, entries: list[CustomerDebtEntry]) -> None:
        entries.sort(
            key=lambda entry: (
                entry.transaction_datetime,
                self._entry_display_order(entry),
                entry.transaction_id,
            ),
            reverse=True,
        )

    def _entry_display_order(self, entry: CustomerHistoryEntry | CustomerDebtEntry) -> int:
        return entry.display_order or self._DEFAULT_DISPLAY_ORDER.get(entry.transaction_kind, 100)

    @staticmethod
    def _entry_sort_datetime(entry: CustomerHistoryEntry | CustomerDebtEntry) -> datetime:
        return entry.sort_datetime or entry.transaction_datetime

    def _ledger_display_order(self, ledger: CustomerBalanceLedger) -> int:
        return ledger.display_order or self._DEFAULT_DISPLAY_ORDER["DEBT_PAYMENT"]

    @staticmethod
    def _debt_ledger_label(ledger: CustomerBalanceLedger) -> str:
        if ledger.event_type == "OPENING_BALANCE":
            return "Nợ đầu kỳ"
        if ledger.event_type in {"BALANCE_ADJUSTMENT", "CUSTOMER_BALANCE_ADJUSTMENT", "ADJUSTMENT", "MANUAL"}:
            return "Điều chỉnh công nợ"
        if ledger.event_type == "INITIAL_DEBT":
            return "Nợ đầu kỳ"
        return ledger.event_type

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

    @staticmethod
    def _reference_effective_datetime(entries: Sequence[CustomerBalanceLedger]) -> datetime:
        return entries[-1].effective_transaction_datetime

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
