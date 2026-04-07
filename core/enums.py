from __future__ import annotations

from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Enum as SAEnum


class UnitMode(StrEnum):
    BAO_KG = "BAO_KG"
    BICH = "BICH"


class UnitType(StrEnum):
    BAO = "BAO"
    KG = "KG"
    BICH = "BICH"


class PaymentMethod(StrEnum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    CARD = "CARD"
    OTHER = "OTHER"


class InvoiceStatus(StrEnum):
    DRAFT = "DRAFT"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class ReturnHandlingMode(StrEnum):
    REFUND_NOW = "REFUND_NOW"
    STORE_CREDIT = "STORE_CREDIT"


UNIT_TYPES_BY_MODE: dict[UnitMode, tuple[UnitType, ...]] = {
    UnitMode.BAO_KG: (UnitType.BAO, UnitType.KG),
    UnitMode.BICH: (UnitType.BICH,),
}

# Canonical inventory conversion note:
# BAO_KG products store stock only in bags; KG is a derived selling/reporting unit.
BAO_TO_KG_RATIO = Decimal("25")



def allowed_unit_types(unit_mode: UnitMode) -> tuple[UnitType, ...]:
    return UNIT_TYPES_BY_MODE[unit_mode]



def build_enum(enum_cls: type[StrEnum], name: str) -> SAEnum:
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        validate_strings=True,
        create_constraint=True,
        values_callable=lambda enum_values: [item.value for item in enum_values],
    )
