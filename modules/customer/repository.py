from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from core.exceptions import NotFoundError
from modules.customer.models import Customer, CustomerBalanceLedger


class CustomerRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    @property
    def session(self) -> Session:
        if self._session is None:
            self._session = self._session_factory()
        return self._session

    def use_session(self, session: Session) -> None:
        self._session = session

    def list_customers(self) -> Sequence[Customer]:
        statement = select(Customer).order_by(Customer.customer_name.asc())
        return self.session.scalars(statement).all()

    def get_customer(self, customer_id: int) -> Customer:
        customer = self.session.get(Customer, customer_id)
        if customer is None:
            raise NotFoundError(f"Không tìm thấy khách {customer_id}.")
        return customer

    def list_ledgers_by_ref(self, customer_id: int, ref_type: str, ref_id: int) -> Sequence[CustomerBalanceLedger]:
        statement = (
            select(CustomerBalanceLedger)
            .where(CustomerBalanceLedger.customer_id == customer_id)
            .where(CustomerBalanceLedger.ref_type == ref_type)
            .where(CustomerBalanceLedger.ref_id == ref_id)
            .order_by(CustomerBalanceLedger.id.asc())
        )
        return self.session.scalars(statement).all()
