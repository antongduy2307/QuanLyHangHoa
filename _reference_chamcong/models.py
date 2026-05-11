from __future__ import annotations

import enum
from datetime import date, datetime
from typing import Any

from sqlalchemy import Boolean
from sqlalchemy import CheckConstraint
from sqlalchemy import Date
from sqlalchemy import DateTime
from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship


class Base(DeclarativeBase):
    pass


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


class Employee(Base):
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

    def __repr__(self) -> str:
        return f"Employee(id={self.id!r}, name={self.name!r}, team={self.team.value!r}, is_active={self.is_active!r})"


class Period(Base):
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

    def __repr__(self) -> str:
        return (
            f"Period(id={self.id!r}, start_date={self.start_date!r}, end_date={self.end_date!r}, "
            f"locked={self.locked!r}, created_at={self.created_at!r})"
        )


class EmployeeShiftPeriod(Base):
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

    def __repr__(self) -> str:
        return (
            f"EmployeeShiftPeriod(id={self.id!r}, employee_id={self.employee_id!r}, "
            f"period_id={self.period_id!r}, shift={self.shift.value!r})"
        )


class DailyRecord(Base):
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

    def __repr__(self) -> str:
        return (
            f"DailyRecord(id={self.id!r}, employee_id={self.employee_id!r}, date={self.date!r}, "
            f"period_id={self.period_id!r}, is_absent={self.is_absent!r}, status={self.status.value!r}, "
            f"total_amount_snapshot={self.total_amount_snapshot!r})"
        )


class WorkType(Base):
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

    def __repr__(self) -> str:
        return (
            f"WorkType(id={self.id!r}, name={self.name!r}, team={self.team.value!r}, "
            f"input_type={self.input_type.value!r}, unit_price={self.unit_price!r}, is_active={self.is_active!r})"
        )


class WorkLog(Base):
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

    def __repr__(self) -> str:
        return (
            f"WorkLog(id={self.id!r}, daily_record_id={self.daily_record_id!r}, "
            f"work_type_id={self.work_type_id!r}, quantity={self.quantity!r}, "
            f"unit_price_snapshot={self.unit_price_snapshot!r}, "
            f"amount_snapshot={self.amount_snapshot!r})"
        )


class BagType(Base):
    __tablename__ = "bag_types"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    unit_price: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    cut_logs: Mapped[list[CutLog]] = relationship(back_populates="bag_type")

    __table_args__ = (
        CheckConstraint("unit_price >= 0", name="ck_bag_type_unit_price_non_negative"),
    )

    def __repr__(self) -> str:
        return (
            f"BagType(id={self.id!r}, name={self.name!r}, unit_price={self.unit_price!r}, "
            f"is_active={self.is_active!r})"
        )


class CutLog(Base):
    __tablename__ = "cut_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    daily_record_id: Mapped[int] = mapped_column(ForeignKey("daily_records.id", ondelete="CASCADE"), nullable=False)
    bag_type_id: Mapped[int] = mapped_column(ForeignKey("bag_types.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_price_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)
    amount_snapshot: Mapped[int] = mapped_column(Integer, nullable=False)

    daily_record: Mapped[DailyRecord] = relationship(back_populates="cut_logs")
    bag_type: Mapped[BagType] = relationship(back_populates="cut_logs")

    __table_args__ = (
        UniqueConstraint("daily_record_id", "bag_type_id", name="uq_cut_log_daily_record_bag_type"),
        CheckConstraint("quantity >= 0", name="ck_cut_log_quantity_non_negative"),
        CheckConstraint("unit_price_snapshot >= 0", name="ck_cut_log_unit_price_non_negative"),
        CheckConstraint("amount_snapshot >= 0", name="ck_cut_log_amount_non_negative"),
    )

    def __repr__(self) -> str:
        return (
            f"CutLog(id={self.id!r}, daily_record_id={self.daily_record_id!r}, bag_type_id={self.bag_type_id!r}, "
            f"quantity={self.quantity!r}, unit_price_snapshot={self.unit_price_snapshot!r}, "
            f"amount_snapshot={self.amount_snapshot!r})"
        )
