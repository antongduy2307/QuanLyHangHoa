from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    event,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base
from core.enums import UnitMode, UnitType, allowed_unit_types, build_enum
from core.exceptions import ValidationError

if TYPE_CHECKING:
    from modules.returns.models import ReturnInvoiceItem
    from modules.sales.models import InvoiceItem


QUANTITY_PRECISION = 14
QUANTITY_SCALE = 3
PRICE_PRECISION = 14
PRICE_SCALE = 2



def _as_decimal(value: Decimal | int | float | str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


class Product(Base):
    """Master product row.

    `unit_mode` defines the domain-level unit family only.
    For BAO_KG products, service may enable BAO, KG, or both prices via `ProductPrice.is_enabled`.
    The database intentionally does not force every BAO_KG product to have both BAO and KG rows.
    """

    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint("length(trim(product_code_base)) > 0", name="ck_products_code_not_blank"),
        CheckConstraint("length(trim(product_name)) > 0", name="ck_products_name_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_code_base: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    product_name: Mapped[str] = mapped_column(String(255), index=True)
    unit_mode: Mapped[UnitMode] = mapped_column(build_enum(UnitMode, "product_unit_mode"))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    prices: Mapped[list[ProductPrice]] = relationship(back_populates="product", cascade="all, delete-orphan")
    inventory_balance: Mapped[InventoryBalance | None] = relationship(back_populates="product", cascade="all, delete-orphan", uselist=False)
    receipt_items: Mapped[list[InventoryReceiptItem]] = relationship(back_populates="product")
    adjustment_items: Mapped[list[InventoryAdjustmentItem]] = relationship(back_populates="product")
    invoice_items: Mapped[list[InvoiceItem]] = relationship(back_populates="product")
    return_items: Mapped[list[ReturnInvoiceItem]] = relationship(back_populates="product")

    def supports_unit_type(self, unit_type: UnitType) -> bool:
        return unit_type in allowed_unit_types(self.unit_mode)

    def validate_price_unit_type(self, unit_type: UnitType) -> None:
        """Local domain helper for service/tests.

        This is intentionally not auto-enforced through ORM events because it depends on
        the parent product row. Service code should call it before persisting cross-row changes.
        """
        if not self.supports_unit_type(unit_type):
            allowed = ", ".join(item.value for item in allowed_unit_types(self.unit_mode))
            raise ValidationError(
                f"Unit type {unit_type.value} is invalid for unit mode {self.unit_mode.value}. Allowed: {allowed}."
            )

    def validate_inventory_balance_fields(
        self,
        *,
        on_hand_bao_decimal: Decimal | None,
        on_hand_bich_integer: Decimal | int | None,
    ) -> None:
        """Local domain helper for canonical inventory storage.

        BAO_KG products store stock only in `on_hand_bao_decimal`.
        BICH products store stock only in `on_hand_bich_integer`.
        KG is not stored as standalone inventory in the database.
        Negative stock is allowed and may persist in DB.
        """
        if self.unit_mode == UnitMode.BAO_KG:
            if on_hand_bao_decimal is None or on_hand_bich_integer is not None:
                raise ValidationError("BAO_KG products must store balance in on_hand_bao_decimal only.")
            return

        if on_hand_bich_integer is None or on_hand_bao_decimal is not None:
            raise ValidationError("BICH products must store balance in on_hand_bich_integer only.")


class ProductPrice(Base):
    """Sellable price row for one product/unit pair.

    `unit_type` must belong to the product's unit family at the domain level.
    `is_enabled` is the switch that decides whether that unit is currently sellable.
    """

    __tablename__ = "product_prices"
    __table_args__ = (
        UniqueConstraint("product_id", "unit_type", name="uq_product_prices_product_unit_type"),
        CheckConstraint("price >= 0", name="ck_product_prices_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), index=True)
    unit_type: Mapped[UnitType] = mapped_column(build_enum(UnitType, "product_price_unit_type"))
    price: Mapped[Decimal] = mapped_column(Numeric(PRICE_PRECISION, PRICE_SCALE), default=Decimal("0"), server_default="0")
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    product: Mapped[Product] = relationship(back_populates="prices")


class InventoryBalance(Base):
    """Canonical inventory balance.

    BAO_KG products store inventory only in bags via `on_hand_bao_decimal`.
    KG is derived later in service/reporting using the 1 bag = 25kg rule.
    BICH products store inventory only in `on_hand_bich_integer`.
    Negative stock is allowed to persist for oversell / correction workflows.
    """

    __tablename__ = "inventory_balances"
    __table_args__ = (
        CheckConstraint(
            "NOT (on_hand_bao_decimal IS NOT NULL AND on_hand_bich_integer IS NOT NULL)",
            name="ck_inventory_balances_single_storage_mode",
        ),
        CheckConstraint(
            "NOT (on_hand_bao_decimal IS NULL AND on_hand_bich_integer IS NULL)",
            name="ck_inventory_balances_some_quantity_present",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), unique=True)
    on_hand_bao_decimal: Mapped[Decimal | None] = mapped_column(Numeric(QUANTITY_PRECISION, QUANTITY_SCALE), nullable=True)
    on_hand_bich_integer: Mapped[Decimal | None] = mapped_column(Numeric(QUANTITY_PRECISION, QUANTITY_SCALE), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    product: Mapped[Product] = relationship(back_populates="inventory_balance")

    def validate_for_product(self, product: Product) -> None:
        """Local helper for service/tests.

        The mapping between product mode and canonical stock column is a cross-row domain rule,
        so it is documented and exposed as an explicit helper instead of an implicit ORM query event.
        """
        product.validate_inventory_balance_fields(
            on_hand_bao_decimal=self.on_hand_bao_decimal,
            on_hand_bich_integer=self.on_hand_bich_integer,
        )


class InventoryReceipt(Base):
    __tablename__ = "inventory_receipts"
    __table_args__ = (
        CheckConstraint("length(trim(receipt_code)) > 0", name="ck_inventory_receipts_code_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    receipt_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list[InventoryReceiptItem]] = relationship(back_populates="receipt", cascade="all, delete-orphan")


class InventoryReceiptItem(Base):
    """Receipt quantity is interpreted by product mode in service code.

    BAO_KG means quantity is bag count; BICH means quantity is pouch count.
    Cross-row validation stays out of ORM events and will be enforced in the service layer.
    """

    __tablename__ = "inventory_receipt_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_inventory_receipt_items_quantity_positive"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("inventory_receipts.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(QUANTITY_PRECISION, QUANTITY_SCALE))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    receipt: Mapped[InventoryReceipt] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="receipt_items")


class InventoryAdjustment(Base):
    __tablename__ = "inventory_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    items: Mapped[list[InventoryAdjustmentItem]] = relationship(back_populates="adjustment", cascade="all, delete-orphan")


class InventoryAdjustmentItem(Base):
    """Adjustment item stores old/new quantity plus the computed delta.

    Only the local arithmetic for `delta_quantity` is enforced here.
    Mode-specific quantity semantics stay in service code.
    `old_quantity` is an audit snapshot of the real pre-adjustment balance and may be negative
    because canonical inventory balances allow negative stock.
    """

    __tablename__ = "inventory_adjustment_items"
    __table_args__ = (
        CheckConstraint("new_quantity >= 0", name="ck_inventory_adjustment_items_new_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    adjustment_id: Mapped[int] = mapped_column(ForeignKey("inventory_adjustments.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    old_quantity: Mapped[Decimal] = mapped_column(Numeric(QUANTITY_PRECISION, QUANTITY_SCALE))
    new_quantity: Mapped[Decimal] = mapped_column(Numeric(QUANTITY_PRECISION, QUANTITY_SCALE))
    delta_quantity: Mapped[Decimal] = mapped_column(Numeric(QUANTITY_PRECISION, QUANTITY_SCALE))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    adjustment: Mapped[InventoryAdjustment] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="adjustment_items")


@event.listens_for(InventoryAdjustmentItem, "before_insert")
@event.listens_for(InventoryAdjustmentItem, "before_update")
def _normalize_inventory_adjustment_item(mapper: object, connection: object, target: InventoryAdjustmentItem) -> None:
    old_quantity = _as_decimal(target.old_quantity)
    new_quantity = _as_decimal(target.new_quantity)
    if old_quantity is None or new_quantity is None:
        raise ValidationError("Adjustment quantities are required.")
    target.delta_quantity = new_quantity - old_quantity
