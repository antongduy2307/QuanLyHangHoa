from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from core.exceptions import ValidationError
from modules.customer.dto import CustomerDTO
from modules.customer.mappers import to_dto
from modules.customer.models import CustomerBalanceLedger
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.sales.models import Invoice
from modules.sales.repository import SalesRepository


@dataclass(frozen=True, slots=True)
class CustomerDetailData:
    customer: CustomerDTO
    recent_invoices: tuple[Invoice, ...]


class CustomerController:
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
            if needle.isdigit():
                customers = [customer for customer in customers if customer.phone and needle in customer.phone]
            else:
                customers = [customer for customer in customers if needle in customer.customer_name.lower()]
        customers = self._apply_debt_filter(customers, only_positive_debt)
        return self._sort_customers(customers, sort_option)

    def create_customer(
        self,
        *,
        customer_name: str,
        phone: str | None,
        address: str | None,
        initial_balance: Decimal,
    ) -> CustomerDTO:
        service = CustomerService(CustomerRepository(self._session_factory))
        customer = service.create_customer(
            customer_name=customer_name,
            phone=phone,
            address=address,
            initial_balance=initial_balance,
        )
        dto = to_dto(customer)
        service._repository.session.close()
        return dto

    def update_customer(
        self,
        customer_id: int,
        *,
        customer_name: str,
        phone: str | None,
        address: str | None,
        current_balance: Decimal,
    ) -> CustomerDTO:
        service = CustomerService(CustomerRepository(self._session_factory))
        customer = service.update_customer(
            customer_id,
            customer_name=customer_name,
            phone=phone,
            address=address,
            target_balance=current_balance,
        )
        dto = to_dto(customer)
        service._repository.session.close()
        return dto

    def pay_debt(self, customer_id: int, amount: Decimal, note: str | None = None) -> object:
        service = CustomerService(CustomerRepository(self._session_factory))
        return service.pay_debt(customer_id, amount, note=note)

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

    def get_customer_with_recent_invoices(self, customer_id: int, limit: int = 3) -> CustomerDetailData:
        customer_repository = CustomerRepository(self._session_factory)
        sales_repository = SalesRepository(self._session_factory)
        customer = customer_repository.get_customer(customer_id)
        invoices = tuple(sales_repository.get_recent_invoices_by_customer(customer_id, limit=limit))
        customer_repository.session.close()
        sales_repository.session.close()
        return CustomerDetailData(customer=to_dto(customer), recent_invoices=invoices)

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
