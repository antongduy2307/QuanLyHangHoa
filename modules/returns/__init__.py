from __future__ import annotations

from core.db import SessionFactory
from modules.returns.repository import ReturnsRepository
from modules.returns.service import ReturnsService
from modules.returns.ui.page import ReturnsPage

MODULE_KEY = "returns"
MODULE_LABEL = "Trả hàng"



def create_page() -> ReturnsPage:
    repository = ReturnsRepository(SessionFactory)
    service = ReturnsService(repository)
    return ReturnsPage(service)
