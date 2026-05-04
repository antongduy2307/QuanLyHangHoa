from __future__ import annotations

from collections.abc import Mapping, Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from core.enums import UnitType
from core.exceptions import ValidationError
from modules.customer.repository import CustomerRepository
from modules.inventory.repository import InventoryRepository
from modules.orders.models import OrderRequest, OrderRequestItem
from modules.orders.repository import OrderRepository


@dataclass(frozen=True, slots=True)
class OrderLineInput:
    product_id: int
    unit_type: UnitType
    quantity: Decimal


class OrderService:
    def __init__(self, repository: OrderRepository) -> None:
        self._repository = repository

    def use_session(self, session: Session) -> None:
        self._repository.use_session(session)

    def list_active_orders(self) -> Sequence[OrderRequest]:
        return self._repository.list_active_orders()

    def get_order(self, order_id: int) -> OrderRequest:
        return self._repository.get_order(order_id)

    def create_order(
        self,
        *,
        customer_id: int | None,
        customer_name_snapshot: str,
        order_datetime: datetime,
        required_delivery_datetime: datetime | None,
        items: list[Mapping[str, object]],
        note: str | None = None,
    ) -> OrderRequest:
        session = self._repository.session
        normalized_datetime = self._require_datetime(order_datetime, "order_datetime")
        normalized_delivery = self._require_optional_datetime(required_delivery_datetime, "required_delivery_datetime")
        normalized_items = self._normalize_items(items)
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            snapshot_name = self._resolve_customer_name(customer_id, customer_name_snapshot)
            order = OrderRequest(
                order_code=self._repository.generate_order_code(normalized_datetime),
                customer_id=customer_id,
                customer_name_snapshot=snapshot_name,
                order_datetime=normalized_datetime,
                required_delivery_datetime=normalized_delivery,
                note=self._normalize_optional_text(note),
                status="OPEN",
            )
            session.add(order)
            session.flush()
            self._replace_items(order, normalized_items)
            session.flush()
            return order

    def update_order(
        self,
        order_id: int,
        *,
        customer_id: int | None,
        customer_name_snapshot: str,
        order_datetime: datetime,
        required_delivery_datetime: datetime | None,
        items: list[Mapping[str, object]],
        note: str | None = None,
    ) -> OrderRequest:
        session = self._repository.session
        normalized_datetime = self._require_datetime(order_datetime, "order_datetime")
        normalized_delivery = self._require_optional_datetime(required_delivery_datetime, "required_delivery_datetime")
        normalized_items = self._normalize_items(items)
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            order = self._repository.get_order(order_id)
            if order.status == "CONVERTED":
                raise ValidationError("Không thể sửa đơn đặt hàng đã chuyển sang hóa đơn.")
            order.customer_id = customer_id
            order.customer_name_snapshot = self._resolve_customer_name(customer_id, customer_name_snapshot)
            order.order_datetime = normalized_datetime
            order.required_delivery_datetime = normalized_delivery
            order.note = self._normalize_optional_text(note)
            self._replace_items(order, normalized_items)
            session.flush()
            return order

    def mark_prepared(self, order_id: int, prepared: bool) -> OrderRequest:
        session = self._repository.session
        transaction_context = nullcontext() if session.in_transaction() else session.begin()
        with transaction_context:
            order = self._repository.get_order(order_id)
            if order.status == "CONVERTED":
                raise ValidationError("Đơn đặt hàng đã chuyển sang hóa đơn.")
            order.status = "PREPARED" if prepared else "OPEN"
            order.completed_at = datetime.now() if prepared else None
            session.flush()
            return order

    def mark_converted(self, order_id: int, invoice_id: int) -> OrderRequest:
        session = self._repository.session
        transaction_context = nullcontext() if session.in_transaction() else session.begin()
        with transaction_context:
            order = self._repository.get_order(order_id)
            order.status = "CONVERTED"
            order.source_invoice_id = int(invoice_id)
            order.completed_at = datetime.now()
            session.flush()
            return order

    def delete_order(self, order_id: int) -> None:
        session = self._repository.session
        transaction_context = nullcontext() if session.in_transaction() else session.begin()
        with transaction_context:
            order = self._repository.get_order(order_id)
            if order.status == "CONVERTED":
                raise ValidationError("Không thể xóa đơn đặt hàng đã chuyển sang hóa đơn.")
            session.delete(order)
            session.flush()

    def _replace_items(self, order: OrderRequest, items: list[OrderLineInput]) -> None:
        inventory_repository = InventoryRepository(self._repository._session_factory)
        inventory_repository.use_session(self._repository.session)
        order.items.clear()
        for line in items:
            product = inventory_repository.get_product(line.product_id)
            product.validate_price_unit_type(line.unit_type)
            order.items.append(
                OrderRequestItem(
                    product_id=product.id,
                    product_name_snapshot=product.product_name,
                    unit_type=line.unit_type,
                    quantity=line.quantity,
                )
            )

    def _resolve_customer_name(self, customer_id: int | None, raw_name: str) -> str:
        if customer_id is None:
            return raw_name.strip() or "Khách lẻ"
        customer_repository = CustomerRepository(self._repository._session_factory)
        customer_repository.use_session(self._repository.session)
        customer = customer_repository.get_customer(customer_id)
        return customer.customer_name

    def _normalize_items(self, items: list[Mapping[str, object]]) -> list[OrderLineInput]:
        if not items:
            raise ValidationError("Đơn đặt hàng phải có ít nhất 1 dòng hàng hóa.")
        return [
            OrderLineInput(
                product_id=int(item["product_id"]),
                unit_type=self._normalize_unit_type(item.get("unit_type")),
                quantity=self._require_positive_decimal(item.get("quantity"), "quantity"),
            )
            for item in items
        ]

    @staticmethod
    def _normalize_unit_type(value: object) -> UnitType:
        if isinstance(value, UnitType):
            return value
        if value is None:
            raise ValidationError("Đơn vị đặt hàng là bắt buộc.")
        try:
            return UnitType(str(value))
        except ValueError as exc:
            raise ValidationError(f"Đơn vị đặt hàng không được hỗ trợ: {value}") from exc

    @staticmethod
    def _require_positive_decimal(value: object, field_name: str) -> Decimal:
        if value is None:
            raise ValidationError(f"{field_name} là bắt buộc.")
        amount = Decimal(str(value))
        if amount <= Decimal("0"):
            raise ValidationError(f"{field_name} phải > 0.")
        return amount

    @staticmethod
    def _require_datetime(value: object, field_name: str) -> datetime:
        if not isinstance(value, datetime):
            raise ValidationError(f"{field_name} phải là datetime hợp lệ.")
        return value

    @staticmethod
    def _require_optional_datetime(value: object, field_name: str) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            raise ValidationError(f"{field_name} phải là datetime hợp lệ.")
        return value

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None
