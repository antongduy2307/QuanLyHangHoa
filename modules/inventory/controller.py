from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session, sessionmaker

from core.enums import UnitMode, UnitType
from modules.inventory.dto import InventoryProductDTO
from modules.inventory.repository import InventoryRepository
from modules.inventory.service import InventoryService


@dataclass(frozen=True, slots=True)
class ProductEditorData:
    product_id: int
    product_code_base: str
    product_name: str
    unit_mode: UnitMode
    enabled_prices: dict[UnitType, Decimal]
    all_prices: dict[UnitType, Decimal]


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

    def get_current_quantity(self, product_id: int) -> Decimal:
        service = InventoryService(InventoryRepository(self._session_factory))
        quantity = service.get_current_quantity(product_id)
        service._repository.session.close()
        return quantity

    def get_unit_display(self, product: InventoryProductDTO) -> str:
        summary = product.enabled_price_summary.upper()
        has_bao = "BAO:" in summary
        has_kg = "KG:" in summary
        has_bich = "BICH:" in summary

        if has_bich:
            return "Bịch"
        if has_bao and has_kg:
            return "Bao + Kg"
        if has_bao:
            return "Bao"
        if has_kg:
            return "Kg"
        if product.unit_mode == UnitMode.BICH.value:
            return "Bịch"
        return "Bao/Kg"

    def get_product_for_edit(self, product_id: int) -> ProductEditorData:
        service = InventoryService(InventoryRepository(self._session_factory))
        product = service.get_product(product_id)
        all_prices: dict[UnitType, Decimal] = {price.unit_type: price.price for price in product.prices}
        enabled_prices: dict[UnitType, Decimal] = {price.unit_type: price.price for price in product.prices if price.is_enabled}
        service._repository.session.close()
        return ProductEditorData(
            product_id=product.id,
            product_code_base=product.product_code_base,
            product_name=product.product_name,
            unit_mode=product.unit_mode,
            enabled_prices=enabled_prices,
            all_prices=all_prices,
        )

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

    def update_product(
        self,
        product_id: int,
        *,
        product_name: str,
        unit_mode: UnitMode,
        enabled_prices: Mapping[UnitType, Decimal],
    ) -> object:
        service = InventoryService(InventoryRepository(self._session_factory))
        return service.update_product(
            product_id,
            product_name=product_name,
            unit_mode=unit_mode,
            enabled_prices=enabled_prices,
        )

    def delete_product(self, product_id: int) -> None:
        service = InventoryService(InventoryRepository(self._session_factory))
        service.delete_product(product_id)

    def create_receipt(self, items: list[Mapping[str, object]]) -> object:
        service = InventoryService(InventoryRepository(self._session_factory))
        return service.create_receipt(items)

    def create_adjustment(self, items: list[Mapping[str, object]]) -> object:
        service = InventoryService(InventoryRepository(self._session_factory))
        return service.create_adjustment(items)
