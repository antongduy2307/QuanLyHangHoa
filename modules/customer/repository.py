from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

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

    def get_ledger(self, ledger_id: int) -> CustomerBalanceLedger:
        statement = (
            select(CustomerBalanceLedger)
            .options(selectinload(CustomerBalanceLedger.customer))
            .where(CustomerBalanceLedger.id == ledger_id)
        )
        ledger = self.session.scalars(statement).one_or_none()
        if ledger is None:
            raise NotFoundError(f"Không tìm thấy giao dịch công nợ {ledger_id}.")
        return ledger

    def list_debt_payments(self) -> Sequence[CustomerBalanceLedger]:
        statement = (
            select(CustomerBalanceLedger)
            .options(selectinload(CustomerBalanceLedger.customer))
            .where(CustomerBalanceLedger.event_type == "DEBT_PAYMENT")
            .order_by(CustomerBalanceLedger.id.desc())
        )
        entries = self.session.scalars(statement).all()
        latest_by_ref_id: dict[int, CustomerBalanceLedger] = {}
        for entry in entries:
            if entry.ref_id not in latest_by_ref_id:
                latest_by_ref_id[entry.ref_id] = entry
        return sorted(latest_by_ref_id.values(), key=lambda item: (item.created_at, item.id), reverse=True)

    def search_debt_payments(self, query: str) -> Sequence[CustomerBalanceLedger]:
        entries = list(self.list_debt_payments())
        needle = query.strip().lower()
        if not needle:
            return entries
        return [
            entry
            for entry in entries
            if entry.customer and needle in entry.customer.customer_name.lower()
        ]

    def list_ledgers_by_ref(self, customer_id: int, ref_type: str, ref_id: int) -> Sequence[CustomerBalanceLedger]:
        statement = (
            select(CustomerBalanceLedger)
            .where(CustomerBalanceLedger.customer_id == customer_id)
            .where(CustomerBalanceLedger.ref_type == ref_type)
            .where(CustomerBalanceLedger.ref_id == ref_id)
            .order_by(CustomerBalanceLedger.id.asc())
        )
        return self.session.scalars(statement).all()

    def list_ledgers_by_event_type(self, customer_id: int, event_type: str) -> Sequence[CustomerBalanceLedger]:
        statement = (
            select(CustomerBalanceLedger)
            .where(CustomerBalanceLedger.customer_id == customer_id)
            .where(CustomerBalanceLedger.event_type == event_type)
            .order_by(CustomerBalanceLedger.id.asc())
        )
        return self.session.scalars(statement).all()

