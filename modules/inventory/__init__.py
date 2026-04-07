from __future__ import annotations

from core.db import SessionFactory
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService
from modules.inventory.ui.page import InventoryPage

MODULE_KEY = "inventory"
MODULE_LABEL = "Hang hoa"



def create_page() -> InventoryPage:
    repository = InventoryRepository(SessionFactory)
    service = InventoryService(repository)
    return InventoryPage(service)
