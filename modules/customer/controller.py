from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from core.exceptions import ValidationError
from modules.customer.dto import CustomerDTO
from modules.customer.mappers import to_dto
from modules.customer.models import Customer
from modules.customer.repository import CustomerRepository
from modules.sales.models import Invoice
from modules.sales.repository import SalesRepository


@dataclass(frozen=True, slots=True)
class CustomerDetailData:
    customer: CustomerDTO
    recent_invoices: tuple[Invoice, ...]


class CustomerController:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_customers(self) -> list[CustomerDTO]:
        repository = CustomerRepository(self._session_factory)
        customers = repository.list_customers()
        repository.session.close()
        return [to_dto(customer) for customer in customers]

    def search_customers(self, query: str) -> list[CustomerDTO]:
        customers = self.list_customers()
        needle = query.strip().lower()
        if not needle:
            return customers
        if needle.isdigit():
            return [customer for customer in customers if customer.phone and needle in customer.phone]
        return [customer for customer in customers if needle in customer.customer_name.lower()]

    def create_customer(self, *, customer_name: str, phone: str | None) -> CustomerDTO:
        repository = CustomerRepository(self._session_factory)
        session = repository.session
        normalized_name = customer_name.strip()
        if not normalized_name:
            raise ValidationError("Ten khach hang khong duoc de trong.")
        normalized_phone = (phone or "").strip() or None
        with session.begin():
            customer = Customer(
                customer_name=normalized_name,
                phone=normalized_phone,
                current_balance=Decimal("0"),
                total_sales=Decimal("0"),
                is_walk_in=False,
            )
            session.add(customer)
            session.flush()
            dto = to_dto(customer)
        session.close()
        return dto

    def update_customer(self, customer_id: int, *, customer_name: str, phone: str | None) -> CustomerDTO:
        repository = CustomerRepository(self._session_factory)
        session = repository.session
        normalized_name = customer_name.strip()
        if not normalized_name:
            raise ValidationError("Ten khach hang khong duoc de trong.")
        normalized_phone = (phone or "").strip() or None
        with session.begin():
            customer = repository.get_customer(customer_id)
            customer.customer_name = normalized_name
            customer.phone = normalized_phone
            session.flush()
            dto = to_dto(customer)
        session.close()
        return dto

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
