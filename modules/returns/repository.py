from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from modules.returns.models import ReturnInvoice


class ReturnsRepository:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_return_invoices(self) -> Sequence[ReturnInvoice]:
        with self._session_factory() as session:
            statement = select(ReturnInvoice).order_by(ReturnInvoice.return_datetime.desc())
            return session.scalars(statement).all()
