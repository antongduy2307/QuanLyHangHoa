from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from modules.customer.dto import CustomerDTO
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
from modules.orders.models import OrderRequest
from modules.orders.repository import OrderRepository
from modules.orders.service import OrderQuantitySummary, OrderService
from modules.sales.controller import SalesController, SellableProductOption


class OrderController:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_active_orders(self) -> Sequence[OrderRequest]:
        repository = OrderRepository(self._session_factory)
        orders = repository.list_active_orders()
        repository.session.close()
        return orders

    def list_active_quantity_summary(self) -> list[OrderQuantitySummary]:
        service = OrderService(OrderRepository(self._session_factory))
        rows = service.list_active_quantity_summary()
        service._repository.session.close()
        return rows

    def get_order(self, order_id: int) -> OrderRequest:
        repository = OrderRepository(self._session_factory)
        order = repository.get_order(order_id)
        repository.session.close()
        return order

    def list_customers(self) -> Sequence[CustomerDTO]:
        service = CustomerService(CustomerRepository(self._session_factory))
        customers = service.list_customers()
        service._repository.session.close()
        return customers

    def list_sellable_products(self) -> list[SellableProductOption]:
        return SalesController(self._session_factory).list_sellable_products()

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
        service = OrderService(OrderRepository(self._session_factory))
        return service.create_order(
            customer_id=customer_id,
            customer_name_snapshot=customer_name_snapshot,
            order_datetime=order_datetime,
            required_delivery_datetime=required_delivery_datetime,
            items=items,
            note=note,
        )

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
        service = OrderService(OrderRepository(self._session_factory))
        return service.update_order(
            order_id,
            customer_id=customer_id,
            customer_name_snapshot=customer_name_snapshot,
            order_datetime=order_datetime,
            required_delivery_datetime=required_delivery_datetime,
            items=items,
            note=note,
        )

    def mark_prepared(self, order_id: int, prepared: bool) -> OrderRequest:
        service = OrderService(OrderRepository(self._session_factory))
        return service.mark_prepared(order_id, prepared)

    def mark_converted(self, order_id: int, invoice_id: int) -> OrderRequest:
        service = OrderService(OrderRepository(self._session_factory))
        return service.mark_converted(order_id, invoice_id)

    def delete_order(self, order_id: int) -> None:
        service = OrderService(OrderRepository(self._session_factory))
        service.delete_order(order_id)

    def order_to_sales_payload(self, order: OrderRequest) -> dict[str, object]:
        products = {product.product_id: product for product in self.list_sellable_products()}
        items: list[dict[str, object]] = []
        for item in order.items:
            product = products.get(item.product_id)
            unit_price = Decimal("0")
            enabled_prices = {}
            stock_by_unit = {}
            product_code = ""
            if product is not None:
                unit_price = product.enabled_prices.get(item.unit_type, Decimal("0"))
                enabled_prices = dict(product.enabled_prices)
                stock_by_unit = dict(product.stock_by_unit)
                product_code = product.product_code_base
            quantity = Decimal(str(item.quantity))
            items.append(
                {
                    "product_id": item.product_id,
                    "product_code_base": product_code,
                    "product_name": item.product_name_snapshot,
                    "unit_type": item.unit_type,
                    "quantity": quantity,
                    "unit_price": unit_price,
                    "line_total": quantity * unit_price,
                    "stock_available": stock_by_unit.get(item.unit_type, Decimal("0")),
                    "enabled_prices": enabled_prices,
                    "stock_by_unit": stock_by_unit,
                }
            )
        return {
            "source_order_id": order.id,
            "customer_id": order.customer_id,
            "customer_name_snapshot": order.customer_name_snapshot,
            "note": order.note,
            "items": items,
        }
