from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class InventoryProductDTO:
    id: int
    product_code_base: str
    product_name: str
    unit_mode: str
    on_hand_display: str
    enabled_price_summary: str
    is_active: bool
    updated_at: datetime
