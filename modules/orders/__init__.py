from __future__ import annotations

from core.db import SessionFactory
from modules.orders.repository import OrderRepository
from modules.orders.service import OrderService

MODULE_KEY = "orders"
MODULE_LABEL = "Đặt hàng"


def create_page():
    from modules.orders.ui.page import OrdersPage

    repository = OrderRepository(SessionFactory)
    service = OrderService(repository)
    return OrdersPage(service)
