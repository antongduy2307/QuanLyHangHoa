from __future__ import annotations

from collections.abc import Mapping, Sequence
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from core.enums import UnitMode, UnitType
from modules.inventory.dto import InventoryProductDTO
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService


class InventoryController:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def list_products(self) -> Sequence[InventoryProductDTO]:
        service = InventoryService(InventoryRepository(self._session_factory))
        return service.list_products()

    def list_product_options(self) -> list[tuple[int, str]]:
        repository = InventoryRepository(self._session_factory)
        products = repository.list_products()
        repository.session.close()
        return [(product.id, f"{product.product_code_base} - {product.product_name}") for product in products]

    def create_product(
        self,
        *,
        product_code_base: str,
        product_name: str,
        unit_mode: UnitMode,
        enabled_prices: Mapping[UnitType, Decimal],
    ) -> object:
        service = InventoryService(InventoryRepository(self._session_factory))
        return service.create_product(
            product_code_base=product_code_base,
            product_name=product_name,
            unit_mode=unit_mode,
            enabled_prices=enabled_prices,
        )

    def create_receipt(self, items: list[Mapping[str, object]]) -> object:
        service = InventoryService(InventoryRepository(self._session_factory))
        return service.create_receipt(items)

    def create_adjustment(self, items: list[Mapping[str, object]]) -> object:
        service = InventoryService(InventoryRepository(self._session_factory))
        return service.create_adjustment(items)
