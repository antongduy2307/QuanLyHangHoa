from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from modules.attendance.models import DailyRecordStatus, Team, WorkInputType


@dataclass(frozen=True, slots=True)
class AttendanceEmployeeRow:
    id: int
    name: str
    team: Team
    status_label: str


@dataclass(frozen=True, slots=True)
class WorkTypeOption:
    id: int
    name: str
    input_type: WorkInputType
    unit_price: int
    is_active: bool


@dataclass(frozen=True, slots=True)
class BagTypeOption:
    id: int
    name: str
    quota_quantity: Decimal
    excess_unit_price: Decimal
    is_active: bool


@dataclass(frozen=True, slots=True)
class WorkLogValue:
    work_type_id: int
    quantity: int
    unit_price_snapshot: int
    amount_snapshot: int


@dataclass(frozen=True, slots=True)
class CutLogValue:
    bag_type_id: int
    quantity: int
    unit_price_snapshot: int
    quota_quantity_snapshot: Decimal | None
    excess_unit_price_snapshot: Decimal | None
    amount_snapshot: int


@dataclass(frozen=True, slots=True)
class DayEntryDTO:
    employee_id: int
    employee_name: str
    team: Team
    selected_date: date
    status_label: str
    record_status: DailyRecordStatus | None
    is_absent: bool
    total_amount_snapshot: int
    work_types: list[WorkTypeOption] = field(default_factory=list)
    bag_types: list[BagTypeOption] = field(default_factory=list)
    work_logs: list[WorkLogValue] = field(default_factory=list)
    cut_logs: list[CutLogValue] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class BlowWorkInput:
    work_type_id: int
    quantity: int | None


@dataclass(frozen=True, slots=True)
class CutWorkInput:
    bag_type_id: int
    quantity: int


@dataclass(frozen=True, slots=True)
class AttendanceSavePayload:
    employee_id: int
    selected_date: date
    is_absent: bool = False
    blow_work: list[BlowWorkInput] = field(default_factory=list)
    cut_work: list[CutWorkInput] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AttendanceSaveResult:
    record_id: int
    status: DailyRecordStatus
    is_absent: bool
    total_amount_snapshot: int
