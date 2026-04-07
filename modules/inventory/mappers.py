from __future__ import annotations

from decimal import Decimal

from core.enums import UnitMode
from modules.inventory.dto import InventoryProductDTO
from modules.inventory.models import Product, ProductPrice


PRICE_ORDER = {"BAO": 0, "KG": 1, "BICH": 2}



def _format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "0"
    return format(value.normalize(), "f").rstrip("0").rstrip(".") or "0"



def _build_on_hand_display(product: Product) -> str:
    # Canonical stock for BAO_KG products is stored in bags only.
    # KG remains a derived reporting/selling unit and is not persisted as standalone inventory.
    balance = product.inventory_balance
    if balance is None:
        return "0"
    if product.unit_mode == UnitMode.BAO_KG:
        return f"{_format_decimal(balance.on_hand_bao_decimal)} bao"
    return f"{balance.on_hand_bich_integer or 0} bich"



def _build_price_summary(prices: list[ProductPrice]) -> str:
    enabled_prices = [price for price in prices if price.is_enabled]
    enabled_prices.sort(key=lambda item: PRICE_ORDER[item.unit_type.value])
    if not enabled_prices:
        return "Chua co gia"
    return ", ".join(f"{item.unit_type.value}: {item.price:,.0f}" for item in enabled_prices)



def to_dto(model: Product) -> InventoryProductDTO:
    return InventoryProductDTO(
        id=model.id,
        product_code_base=model.product_code_base,
        product_name=model.product_name,
        unit_mode=model.unit_mode.value,
        on_hand_display=_build_on_hand_display(model),
        enabled_price_summary=_build_price_summary(list(model.prices)),
        is_active=model.is_active,
        updated_at=model.updated_at,
    )
