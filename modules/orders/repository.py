from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from core.exceptions import NotFoundError
from modules.orders.models import OrderRequest


class OrderRepository:
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

    def generate_order_code(self, order_datetime: datetime) -> str:
        prefix = f"DH{order_datetime.strftime('%Y%m%d')}-"
        statement = (
            select(OrderRequest.order_code)
            .where(OrderRequest.order_code.like(f"{prefix}%"))
            .order_by(OrderRequest.order_code.desc())
            .limit(1)
        )
        last_code = self.session.scalar(statement)
        next_number = int(last_code.rsplit("-", 1)[1]) + 1 if last_code else 1
        return f"{prefix}{next_number:03d}"

    def get_order(self, order_id: int) -> OrderRequest:
        statement = (
            select(OrderRequest)
            .options(selectinload(OrderRequest.items))
            .where(OrderRequest.id == order_id)
        )
        order = self.session.scalars(statement).one_or_none()
        if order is None:
            raise NotFoundError(f"Không tìm thấy đơn đặt hàng {order_id}.")
        return order

    def list_active_orders(self) -> Sequence[OrderRequest]:
        statement = (
            select(OrderRequest)
            .options(selectinload(OrderRequest.items))
            .where(OrderRequest.status.in_(("OPEN", "PREPARED")))
            .order_by(
                OrderRequest.status.desc(),
                OrderRequest.required_delivery_datetime.asc().nulls_last(),
                OrderRequest.order_datetime.asc(),
                OrderRequest.id.asc(),
            )
        )
        return self.session.scalars(statement).all()
