from __future__ import annotations

from core.db import SessionFactory
from modules.sales.repository import SalesRepository
from modules.sales.service import SalesService

MODULE_KEY = "sales"
MODULE_LABEL = "Bán hàng"


def create_page():
    from modules.sales.ui.page import SalesPage

    repository = SalesRepository(SessionFactory)
    service = SalesService(repository)
    return SalesPage(service)
