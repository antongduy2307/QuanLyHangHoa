from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import or_, select
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
        return self._latest_debt_payments(entries)

    def get_recent_debt_payments_by_customer(self, customer_id: int, limit: int = 3) -> Sequence[CustomerBalanceLedger]:
        statement = (
            select(CustomerBalanceLedger)
            .options(selectinload(CustomerBalanceLedger.customer))
            .where(CustomerBalanceLedger.customer_id == customer_id)
            .where(CustomerBalanceLedger.event_type == "DEBT_PAYMENT")
            .order_by(CustomerBalanceLedger.id.desc())
        )
        entries = self.session.scalars(statement).all()
        return self._latest_debt_payments(entries)[:limit]

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

    def list_debt_payment_ref_ids_by_source(
        self,
        customer_id: int,
        source_ref_type: str,
        source_ref_id: int,
        *,
        legacy_note: str | None = None,
    ) -> Sequence[int]:
        source_filter = (
            (CustomerBalanceLedger.source_ref_type == source_ref_type)
            & (CustomerBalanceLedger.source_ref_id == source_ref_id)
        )
        if legacy_note:
            source_filter = or_(source_filter, CustomerBalanceLedger.note == legacy_note)
        statement = (
            select(CustomerBalanceLedger.ref_id)
            .where(CustomerBalanceLedger.customer_id == customer_id)
            .where(CustomerBalanceLedger.ref_type == "DEBT_PAYMENT")
            .where(CustomerBalanceLedger.event_type == "DEBT_PAYMENT")
            .where(source_filter)
            .order_by(CustomerBalanceLedger.ref_id.asc())
            .distinct()
        )
        return self.session.scalars(statement).all()

    def list_balance_ledgers_by_customer(self, customer_id: int) -> Sequence[CustomerBalanceLedger]:
        statement = (
            select(CustomerBalanceLedger)
            .options(selectinload(CustomerBalanceLedger.customer))
            .where(CustomerBalanceLedger.customer_id == customer_id)
            .order_by(
                CustomerBalanceLedger.transaction_datetime.asc(),
                CustomerBalanceLedger.display_order.asc(),
                CustomerBalanceLedger.id.asc(),
            )
        )
        return self.session.scalars(statement).all()

    def list_debt_payments_by_customer(self, customer_id: int) -> Sequence[CustomerBalanceLedger]:
        statement = (
            select(CustomerBalanceLedger)
            .options(selectinload(CustomerBalanceLedger.customer))
            .where(CustomerBalanceLedger.customer_id == customer_id)
            .where(CustomerBalanceLedger.event_type == "DEBT_PAYMENT")
            .order_by(CustomerBalanceLedger.id.desc())
        )
        entries = self.session.scalars(statement).all()
        return self._latest_debt_payments(entries)

    def has_business_history(self, customer_id: int) -> bool:
        from modules.returns.models import ReturnInvoice
        from modules.sales.models import Invoice

        invoice_exists = self.session.scalar(
            select(Invoice.id).where(Invoice.customer_id == customer_id).limit(1)
        )
        if invoice_exists is not None:
            return True

        return_exists = self.session.scalar(
            select(ReturnInvoice.id).where(ReturnInvoice.customer_id == customer_id).limit(1)
        )
        if return_exists is not None:
            return True

        ledger_exists = self.session.scalar(
            select(CustomerBalanceLedger.id).where(CustomerBalanceLedger.customer_id == customer_id).limit(1)
        )
        return ledger_exists is not None

    def has_trade_or_debt_history(self, customer_id: int) -> bool:
        from modules.returns.models import ReturnInvoice
        from modules.sales.models import Invoice

        invoice_exists = self.session.scalar(select(Invoice.id).where(Invoice.customer_id == customer_id).limit(1))
        if invoice_exists is not None:
            return True

        return_exists = self.session.scalar(select(ReturnInvoice.id).where(ReturnInvoice.customer_id == customer_id).limit(1))
        if return_exists is not None:
            return True

        debt_payment_exists = self.session.scalar(
            select(CustomerBalanceLedger.id)
            .where(CustomerBalanceLedger.customer_id == customer_id)
            .where(CustomerBalanceLedger.event_type == "DEBT_PAYMENT")
            .limit(1)
        )
        return debt_payment_exists is not None

    def _latest_debt_payments(self, entries: Sequence[CustomerBalanceLedger]) -> list[CustomerBalanceLedger]:
        latest_by_ref_id: dict[int, CustomerBalanceLedger] = {}
        for entry in entries:
            if entry.ref_id not in latest_by_ref_id:
                latest_by_ref_id[entry.ref_id] = entry
        return sorted(
            latest_by_ref_id.values(),
            key=lambda item: (item.effective_transaction_datetime, item.id),
            reverse=True,
        )

