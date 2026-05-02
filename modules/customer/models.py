from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import Base

if TYPE_CHECKING:
    from modules.sales.models import Invoice


AMOUNT_PRECISION = 14
AMOUNT_SCALE = 2


class Customer(Base):
    """Customer ledger anchor.

    `current_balance` may be negative depending on payment/return flow.
    `total_sales` is a service-maintained net sales aggregate, not a DB-derived total.
    Any balance change must be accompanied by a ledger entry in service code; the model does not auto-write ledger rows.
    """

    __tablename__ = "customers"
    __table_args__ = (
        CheckConstraint("length(trim(customer_name)) > 0", name="ck_customers_name_not_blank"),
        CheckConstraint("total_sales >= 0", name="ck_customers_total_sales_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_name: Mapped[str] = mapped_column(String(255), index=True)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    address: Mapped[str | None] = mapped_column(String(255), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_balance: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), default=Decimal("0"), server_default="0")
    total_sales: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE), default=Decimal("0"), server_default="0")
    is_walk_in: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    invoices: Mapped[list[Invoice]] = relationship(back_populates="customer")
    balance_ledger_entries: Mapped[list[CustomerBalanceLedger]] = relationship(back_populates="customer", cascade="all, delete-orphan")


class CustomerBalanceLedger(Base):
    """Append-only balance history row written by service code."""

    __tablename__ = "customer_balance_ledgers"
    __table_args__ = (
        CheckConstraint("length(trim(event_type)) > 0", name="ck_customer_balance_ledgers_event_type_not_blank"),
        CheckConstraint("length(trim(ref_type)) > 0", name="ck_customer_balance_ledgers_ref_type_not_blank"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"), index=True)
    event_type: Mapped[str] = mapped_column(String(50))
    ref_type: Mapped[str] = mapped_column(String(50))
    ref_id: Mapped[int] = mapped_column(Integer)
    source_ref_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_ref_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    display_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    amount_delta: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE))
    balance_after: Mapped[Decimal] = mapped_column(Numeric(AMOUNT_PRECISION, AMOUNT_SCALE))
    transaction_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    customer: Mapped[Customer] = relationship(back_populates="balance_ledger_entries")

    @property
    def effective_transaction_datetime(self) -> datetime:
        return self.transaction_datetime or self.created_at
