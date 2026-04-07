from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

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
        statement = select(ReturnInvoice).order_by(ReturnInvoice.return_datetime.desc())
        return self.session.scalars(statement).all()

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
