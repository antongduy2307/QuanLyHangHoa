from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base
from core.enums import InvoiceStatus, PaymentMethod, UnitType, build_enum
from modules.inventory.models import Product

if TYPE_CHECKING:
    from modules.customer.models import Customer
    from modules.returns.models import ReturnInvoice, ReturnInvoiceItem


AMOUNT_PRECISION = 14
AMOUNT_SCALE = 2
QUANTITY_PRECISION = 14
QUANTITY_SCALE = 3


class Invoice(Base):
    """Sales invoice header.

    `customer_id` stays nullable for walk-in sales.
    `customer_snapshot_name` must always be stored so the invoice can still render the original name
    even if the customer row changes later or no customer row existed at all.
    Invoice debt updates, rollback/reapply behavior, and header-total orchestration belong to service code.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        CheckConstraint("length(trim(invoice_code)) > 0", name="ck_invoices_code_not_blank"),
        CheckConstraint("length(trim(customer_snapshot_name)) > 0", name="ck_invoices_customer_snapshot_not_blank"),
        CheckConstraint("total_amount >= 0", name="ck_invoices_total_amount_non_negative"),
        CheckConstraint("paid_amount IS NULL OR paid_amount >= 0", name="ck_invoices_paid_amount_non_negative"),
        CheckConstraint("paid_amount IS NULL OR paid_amount <= total_amount", name="ck_invoices_paid_amount_lte_total"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_snapshot_name: Mapped[str] = mapped_column(String(255))
    invoice_datetime: Mapped[datetime] = mapped_column(DateTime, index=True, server_default=func.now())
    total_amount: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), default=Decimal("0"), server_default="0")
    paid_amount: Mapped[Decimal | None] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), nullable=True)
    payment_method: Mapped[PaymentMethod | None] = mapped_column(build_enum(PaymentMethod, "invoice_payment_method"), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[InvoiceStatus] = mapped_column(build_enum(InvoiceStatus, "invoice_status"), default=InvoiceStatus.DRAFT, server_default=InvoiceStatus.DRAFT.value)

    customer: Mapped[Customer | None] = relationship(back_populates="invoices")
    items: Mapped[list[InvoiceItem]] = relationship(back_populates="invoice", cascade="all, delete-orphan")
    source_returns: Mapped[list[ReturnInvoice]] = relationship(back_populates="source_invoice")


class InvoiceItem(Base):
    """Immutable item snapshot captured at sell time.

    Snapshot fields (`product_code_snapshot`, `product_name_snapshot`, `unit_price`, `line_total`)
    intentionally do not depend on the product's current name or current pricing after the invoice is created.
    Cross-entity rules such as unit compatibility or sale quantity semantics are deferred to service code.
    """

    __tablename__ = "invoice_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_invoice_items_quantity_positive"),
        CheckConstraint("unit_price >= 0", name="ck_invoice_items_unit_price_non_negative"),
        CheckConstraint("line_total >= 0", name="ck_invoice_items_line_total_non_negative"),
        CheckConstraint("length(trim(product_code_snapshot)) > 0", name="ck_invoice_items_product_code_snapshot_not_blank"),
        CheckConstraint("length(trim(product_name_snapshot)) > 0", name="ck_invoice_items_product_name_snapshot_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invoice_id: Mapped[int] = mapped_column(ForeignKey("invoices.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    unit_type: Mapped[UnitType] = mapped_column(build_enum(UnitType, "invoice_item_unit_type"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(QUANTITY_PRECISION, QUANTITY_SCALE))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE))
    line_total: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE))
    product_code_snapshot: Mapped[str] = mapped_column(String(64))
    product_name_snapshot: Mapped[str] = mapped_column(String(255))

    invoice: Mapped[Invoice] = relationship(back_populates="items")
    product: Mapped[Product] = relationship(back_populates="invoice_items")
    return_items: Mapped[list[ReturnInvoiceItem]] = relationship(back_populates="source_invoice_item")
