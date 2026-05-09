from __future__ import annotations

import enum
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import Boolean, CheckConstraint, Date, DateTime, Numeric
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from modules.attendance.db import AttendanceBase


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    return [member.value for member in enum_cls]


class Team(enum.StrEnum):
    BLOW = "blow"
    CUT = "cut"


class Shift(enum.StrEnum):
    DAY = "day"
    NIGHT = "night"


class DailyRecordStatus(enum.StrEnum):
    DRAFT = "draft"
    DONE = "done"


class WorkInputType(enum.StrEnum):
    TICK = "tick"
    QUANTITY = "quantity"


class Employee(AttendanceBase):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    team: Mapped[Team] = mapped_column(
        SAEnum(Team, name="team_enum", native_enum=False, values_callable=_enum_values),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    shift_periods: Mapped[list[EmployeeShiftPeriod]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    daily_records: Mapped[list[DailyRecord]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
    )


class Period(AttendanceBase):
    __tablename__ = "periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    locked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, default=datetime.utcnow)

    employee_shift_periods: Mapped[list[EmployeeShiftPeriod]] = relationship(
        back_populates="period",
        cascade="all, delete-orphan",
    )
    daily_records: Mapped[list[DailyRecord]] = relationship(
        back_populates="period",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint("start_date <= end_date", name="ck_period_date_order"),
        UniqueConstraint("start_date", "end_date", name="uq_period_start_date_end_date"),
    )


class EmployeeShiftPeriod(AttendanceBase):
    __tablename__ = "employee_shift_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id", ondelete="CASCADE"), nullable=False)
    shift: Mapped[Shift] = mapped_column(
        SAEnum(Shift, name="shift_enum", native_enum=False, values_callable=_enum_values),
        nullable=False,
    )

    employee: Mapped[Employee] = relationship(back_populates="shift_periods")
    period: Mapped[Period] = relationship(back_populates="employee_shift_periods")

    __table_args__ = (
        UniqueConstraint("employee_id", "period_id", name="uq_employee_shift_period_employee_period"),
    )


class DailyRecord(AttendanceBase):
    __tablename__ = "daily_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id", ondelete="CASCADE"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    period_id: Mapped[int] = mapped_column(ForeignKey("periods.id", ondelete="CASCADE"), nullable=False)
    is_absent: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="0")
    status: Mapped[DailyRecordStatus] = mapped_column(
        SAEnum(DailyRecordStatus, name="daily_record_status_enum", native_enum=False, values_callable=_enum_values),
        nullable=False,
        default=DailyRecordStatus.DRAFT,
        server_default=DailyRecordStatus.DRAFT.value,
    )
    total_amount_snapshot: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    employee: Mapped[Employee] = relationship(back_populates="daily_records")
    period: Mapped[Period] = relationship(back_populates="daily_records")
    work_logs: Mapped[list[WorkLog]] = relationship(
        back_populates="daily_record",
        cascade="all, delete-orphan",
    )
    cut_logs: Mapped[list[CutLog]] = relationship(
        back_populates="daily_record",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("employee_id", "date", name="uq_daily_record_employee_date"),
        CheckConstraint("total_amount_snapshot >= 0", name="ck_daily_record_total_amount_non_negative"),
    )


class WorkType(AttendanceBase):
    __tablename__ = "work_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    team: Mapped[Team] = mapped_column(
        SAEnum(Team, name="work_type_team_enum", native_enum=False, values_callable=_enum_values),
        nullable=False,
        default=Team.BLOW,
        server_default=Team.BLOW.value,
    )
    input_type: Mapped[WorkInputType] = mapped_column(
        SAEnum(WorkInputType, name="work_input_type_enum", native_enum=False, values_callable=_enum_values),
        nullable=False,
    )
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    work_logs: Mapped[list[WorkLog]] = relationship(back_populates="work_type")

    __table_args__ = (
        CheckConstraint("team = 'blow'", name="ck_work_type_team_blow"),
        CheckConstraint("unit_price >= 0", name="ck_work_type_unit_price_non_negative"),
        UniqueConstraint("team", "name", name="uq_work_type_team_name"),
    )


class WorkLog(AttendanceBase):
    __tablename__ = "work_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_record_id: Mapped[int] = mapped_column(ForeignKey("daily_records.id", ondelete="CASCADE"), nullable=False)
    work_type_id: Mapped[int] = mapped_column(ForeignKey("work_types.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)

    daily_record: Mapped[DailyRecord] = relationship(back_populates="work_logs")
    work_type: Mapped[WorkType] = relationship(back_populates="work_logs")

    __table_args__ = (
        CheckConstraint("quantity >= 1", name="ck_work_log_quantity_positive"),
        CheckConstraint("unit_price_snapshot >= 0", name="ck_work_log_unit_price_non_negative"),
        CheckConstraint("amount_snapshot >= 0", name="ck_work_log_amount_non_negative"),
        UniqueConstraint("daily_record_id", "work_type_id", name="uq_work_log_daily_work_type"),
    )


class BagType(AttendanceBase):
    __tablename__ = "bag_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    quota_quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    excess_unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    cut_logs: Mapped[list[CutLog]] = relationship(back_populates="bag_type")

    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_bag_type_unit_price_non_negative"),
        CheckConstraint("quota_quantity >= 0", name="ck_bag_type_quota_quantity_non_negative"),
        CheckConstraint("excess_unit_price >= 0", name="ck_bag_type_excess_unit_price_non_negative"),
    )


class CutLog(AttendanceBase):
    __tablename__ = "cut_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_record_id: Mapped[int] = mapped_column(ForeignKey("daily_records.id", ondelete="CASCADE"), nullable=False)
    bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    quota_quantity_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    excess_unit_price_snapshot: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    amount_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)

    daily_record: Mapped[DailyRecord] = relationship(back_populates="cut_logs")
    bag_type: Mapped[BagType] = relationship(back_populates="cut_logs")

    __table_args__ = (
        UniqueConstraint("daily_record_id", "bag_type_id", name="uq_cut_log_daily_record_bag_type"),
        CheckConstraint("quantity >= 0", name="ck_cut_log_quantity_non_negative"),
        CheckConstraint("unit_price_snapshot >= 0", name="ck_cut_log_unit_price_non_negative"),
        CheckConstraint(
            "quota_quantity_snapshot IS NULL OR quota_quantity_snapshot >= 0",
            name="ck_cut_log_quota_quantity_non_negative",
        ),
        CheckConstraint(
            "excess_unit_price_snapshot IS NULL OR excess_unit_price_snapshot >= 0",
            name="ck_cut_log_excess_unit_price_non_negative",
        ),
        CheckConstraint("amount_snapshot >= 0", name="ck_cut_log_amount_non_negative"),
    )
