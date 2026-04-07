from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from modules.sales.models import Invoice


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
        statement = select(Invoice).order_by(Invoice.invoice_datetime.desc())
        return self.session.scalars(statement).all()

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

    def get_invoice(self, invoice_id: int) -> Invoice | None:
        statement = (
            select(Invoice)
            .options(selectinload(Invoice.items))
            .where(Invoice.id == invoice_id)
        )
        return self.session.scalars(statement).one_or_none()
