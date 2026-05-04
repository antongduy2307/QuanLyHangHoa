from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base
from core.enums import UnitType, build_enum

if TYPE_CHECKING:
    from modules.customer.models import Customer
    from modules.inventory.models import Product
    from modules.sales.models import Invoice


QUANTITY_PRECISION = 14
QUANTITY_SCALE = 3


class OrderRequest(Base):
    __tablename__ = "order_requests"
    __table_args__ = (
        CheckConstraint("length(trim(order_code)) > 0", name="ck_order_requests_code_not_blank"),
        CheckConstraint("length(trim(customer_name_snapshot)) > 0", name="ck_order_requests_customer_snapshot_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id", ondelete="SET NULL"), nullable=True, index=True)
    customer_name_snapshot: Mapped[str] = mapped_column(String(255))
    order_datetime: Mapped[datetime] = mapped_column(DateTime, index=True, server_default=func.now())
    required_delivery_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="OPEN", server_default="OPEN", index=True)
    source_invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    customer: Mapped[Customer | None] = relationship()
    source_invoice: Mapped[Invoice | None] = relationship()
    items: Mapped[list[OrderRequestItem]] = relationship(back_populates="order", cascade="all, delete-orphan")


class OrderRequestItem(Base):
    __tablename__ = "order_request_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_request_items_quantity_positive"),
        CheckConstraint("length(trim(product_name_snapshot)) > 0", name="ck_order_request_items_product_name_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("order_requests.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="RESTRICT"), index=True)
    product_name_snapshot: Mapped[str] = mapped_column(String(255))
    unit_type: Mapped[UnitType] = mapped_column(build_enum(UnitType, "order_request_item_unit_type"))
    quantity: Mapped[Decimal] = mapped_column(Numeric(QUANTITY_PRECISION, QUANTITY_SCALE))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    order: Mapped[OrderRequest] = relationship(back_populates="items")
    product: Mapped[Product] = relationship()
