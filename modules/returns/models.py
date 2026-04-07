from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base
from core.enums import ReturnHandlingMode, UnitType, build_enum
from modules.inventory.models import Product
from modules.sales.models import Invoice, InvoiceItem


QUANTITY_PRECISION = 14
QUANTITY_SCALE = 3
AMOUNT_PRECISION = 14
AMOUNT_SCALE = 2


class ReturnInvoice(Base):
    """Return bill header.

    Returns are represented as standalone bills and never mutate the source invoice row in place.
    `handling_mode` stores whether the customer is refunded immediately or receives store credit.
    Quantity ceilings and financial allocation rules belong to service code.
    """

    __tablename__ = "return_invoices"
    __table_args__ = (
        CheckConstraint("length(trim(return_code)) > 0", name="ck_return_invoices_code_not_blank"),
        CheckConstraint("total_amount >= 0", name="ck_return_invoices_total_amount_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    return_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    source_invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="RESTRICT"), index=True)
    return_datetime: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    total_amount: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), default=Decimal("0"), server_default="0")
    handling_mode: Mapped[ReturnHandlingMode] = mapped_column(
        build_enum(ReturnHandlingMode, "return_handling_mode"),
        default=ReturnHandlingMode.STORE_CREDIT,
        server_default=ReturnHandlingMode.STORE_CREDIT.value,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    source_invoice: Mapped[Invoice] = relationship(back_populates="source_returns")
    items: Mapped[list[ReturnInvoiceItem]] = relationship(back_populates="return_invoice", cascade="all, delete-orphan")


class ReturnInvoiceItem(Base):
    """Return item snapshot linked back to the source sale line.

    `source_invoice_item_id` is required so service code can enforce return ceilings later.
    The database keeps the reference, but does not try to encode complex source-vs-return quantity rules.
    """

    __tablename__ = "return_invoice_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_return_invoice_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_return_invoice_items_unit_price_non_negative"),
        CheckConstraint("line_total >= 0", name="ck_return_invoice_items_line_total_non_negative"),
        CheckConstraint("length(trim(product_code_snapshot)) > 0", name="ck_return_invoice_items_product_code_snapshot_not_blank"),
        CheckConstraint("length(trim(product_name_snapshot)) > 0", name="ck_return_invoice_items_product_name_snapshot_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    return_invoice_id: Mapped[int] = mapped_column(ForeignKey("return_invoices.id", ondelete="CASCADE"), index=True)
    source_invoice_item_id: Mapped[int] = mapped_column(ForeignKey("invoice_items.id", ondelete="RESTRICT"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    unit_type: Mapped[UnitType] = mapped_column(build_enum(UnitType, "return_invoice_item_unit_type"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(QUANTITY_PRECISION, QUANTITY_SCALE))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE))
    line_total: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE))
    product_code_snapshot: Mapped[str] = mapped_column(String(64))
    product_name_snapshot: Mapped[str] = mapped_column(String(255))

    return_invoice: Mapped[ReturnInvoice] = relationship(back_populates="items")
    source_invoice_item: Mapped[InvoiceItem] = relationship(back_populates="return_items")
    product: Mapped[Product] = relationship(back_populates="return_items")
