from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from core.exceptions import NotFoundError
from modules.returns.models import ReturnInvoice, ReturnInvoiceItem


class ReturnsRepository:
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

    def list_return_invoices(self) -> Sequence[ReturnInvoice]:
        statement = (
            select(ReturnInvoice)
            .options(
                selectinload(ReturnInvoice.items),
                selectinload(ReturnInvoice.source_invoice),
                selectinload(ReturnInvoice.customer),
            )
            .order_by(ReturnInvoice.return_datetime.desc())
        )
        return self.session.scalars(statement).all()

    def search_return_invoices_by_customer_name(self, query: str, limit: int = 20) -> Sequence[ReturnInvoice]:
        needle = query.strip()
        statement = (
            select(ReturnInvoice)
            .options(
                selectinload(ReturnInvoice.items),
                selectinload(ReturnInvoice.source_invoice),
                selectinload(ReturnInvoice.customer),
            )
            .order_by(ReturnInvoice.return_datetime.desc())
            .limit(limit)
        )
        if needle:
            statement = (
                select(ReturnInvoice)
                .options(
                    selectinload(ReturnInvoice.items),
                    selectinload(ReturnInvoice.source_invoice),
                    selectinload(ReturnInvoice.customer),
                )
                .where(ReturnInvoice.customer_snapshot_name.ilike(f"%{needle}%"))
                .order_by(ReturnInvoice.return_datetime.desc())
                .limit(limit)
            )
        return self.session.scalars(statement).all()

    def get_recent_return_invoices_by_customer(self, customer_id: int, limit: int = 3) -> Sequence[ReturnInvoice]:
        statement = (
            select(ReturnInvoice)
            .options(
                selectinload(ReturnInvoice.items),
                selectinload(ReturnInvoice.source_invoice),
                selectinload(ReturnInvoice.customer),
            )
            .where(ReturnInvoice.customer_id == customer_id)
            .order_by(ReturnInvoice.return_datetime.desc())
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def list_return_invoices_by_customer(self, customer_id: int) -> Sequence[ReturnInvoice]:
        statement = (
            select(ReturnInvoice)
            .options(
                selectinload(ReturnInvoice.items),
                selectinload(ReturnInvoice.source_invoice),
                selectinload(ReturnInvoice.customer),
            )
            .where(ReturnInvoice.customer_id == customer_id)
            .order_by(ReturnInvoice.return_datetime.desc())
        )
        return self.session.scalars(statement).all()

    def get_return_invoice(self, return_invoice_id: int) -> ReturnInvoice:
        statement = (
            select(ReturnInvoice)
            .options(
                selectinload(ReturnInvoice.items),
                selectinload(ReturnInvoice.source_invoice),
                selectinload(ReturnInvoice.customer),
            )
            .where(ReturnInvoice.id == return_invoice_id)
        )
        return_invoice = self.session.scalars(statement).one_or_none()
        if return_invoice is None:
            raise NotFoundError(f"Return invoice {return_invoice_id} was not found.")
        return return_invoice

    def generate_return_code(self, return_datetime: datetime) -> str:
        prefix = f"TR{return_datetime.strftime('%Y%m%d')}-"
        statement = (
            select(ReturnInvoice.return_code)
            .where(ReturnInvoice.return_code.like(f"{prefix}%"))
            .order_by(ReturnInvoice.return_code.desc())
            .limit(1)
        )
        last_code = self.session.scalar(statement)
        next_number = int(last_code.rsplit("-", 1)[1]) + 1 if last_code else 1
        return f"{prefix}{next_number:03d}"

    def get_total_returned_quantity(self, source_invoice_item_id: int) -> Decimal:
        statement = select(func.coalesce(func.sum(ReturnInvoiceItem.quantity), 0)).where(
            ReturnInvoiceItem.source_invoice_item_id == source_invoice_item_id
        )
        result = self.session.scalar(statement)
        return Decimal(str(result or 0))

    def get_total_returned_quantity_excluding_return(self, source_invoice_item_id: int, return_invoice_id: int) -> Decimal:
        statement = (
            select(func.coalesce(func.sum(ReturnInvoiceItem.quantity), 0))
            .where(ReturnInvoiceItem.source_invoice_item_id == source_invoice_item_id)
            .where(ReturnInvoiceItem.return_invoice_id != return_invoice_id)
        )
        result = self.session.scalar(statement)
        return Decimal(str(result or 0))
