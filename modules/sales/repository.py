from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from core.exceptions import NotFoundError
from modules.sales.models import Invoice, InvoiceItem


class SalesRepository:
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

    def list_invoices(self) -> Sequence[Invoice]:
        statement = select(Invoice).options(selectinload(Invoice.items)).order_by(Invoice.invoice_datetime.desc())
        return self.session.scalars(statement).all()

    def search_invoices_by_customer_name(self, query: str, limit: int = 20) -> Sequence[Invoice]:
        needle = query.strip()
        statement = select(Invoice).options(selectinload(Invoice.items)).order_by(Invoice.invoice_datetime.desc()).limit(limit)
        if needle:
            statement = (
                select(Invoice)
                .options(selectinload(Invoice.items))
                .where(Invoice.customer_snapshot_name.ilike(f"%{needle}%"))
                .order_by(Invoice.invoice_datetime.desc())
                .limit(limit)
            )
        return self.session.scalars(statement).all()

    def get_recent_invoices_by_customer(self, customer_id: int, limit: int = 3) -> Sequence[Invoice]:
        statement = (
            select(Invoice)
            .where(Invoice.customer_id == customer_id)
            .order_by(Invoice.invoice_datetime.desc())
            .limit(limit)
        )
        return self.session.scalars(statement).all()

    def get_invoice(self, invoice_id: int) -> Invoice:
        statement = (
            select(Invoice)
            .options(selectinload(Invoice.items))
            .where(Invoice.id == invoice_id)
        )
        invoice = self.session.scalars(statement).one_or_none()
        if invoice is None:
            raise NotFoundError(f"Invoice {invoice_id} was not found.")
        return invoice

    def get_invoice_item(self, invoice_item_id: int) -> InvoiceItem:
        item = self.session.get(InvoiceItem, invoice_item_id)
        if item is None:
            raise NotFoundError(f"Invoice item {invoice_item_id} was not found.")
        return item

    def generate_invoice_code(self, invoice_datetime: datetime) -> str:
        prefix = f"HD{invoice_datetime.strftime('%Y%m%d')}-"
        statement = (
            select(Invoice.invoice_code)
            .where(Invoice.invoice_code.like(f"{prefix}%"))
            .order_by(Invoice.invoice_code.desc())
            .limit(1)
        )
        last_code = self.session.scalar(statement)
        next_number = int(last_code.rsplit("-", 1)[1]) + 1 if last_code else 1
        return f"{prefix}{next_number:03d}"
