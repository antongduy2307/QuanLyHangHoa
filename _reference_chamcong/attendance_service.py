from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import DailyRecord
from models import DailyRecordStatus
from models import EmployeeShiftPeriod
from models import Period
from models import Team
from services import add_blow_work
from services import add_cut_work
from services import create_period
from services import get_or_create_daily_record
from services import set_daily_record_absent


@dataclass(frozen=True)
class AttendanceSaveResult:
    record_id: int
    status: DailyRecordStatus
    is_absent: bool


def ensure_period_for_date(session: Session, selected_day: date) -> None:
    period = session.scalar(
        select(Period).where(
            Period.start_date <= selected_day,
            Period.end_date >= selected_day,
        )
    )
    if period is not None:
        return

    start_day, end_day = _calculate_cycle_bounds(selected_day)
    create_period(session, start_day, end_day)


def get_daily_record(session: Session, employee_id: int, selected_day: date) -> DailyRecord | None:
    return session.scalar(
        select(DailyRecord).where(
            DailyRecord.employee_id == employee_id,
            DailyRecord.date == selected_day,
        )
    )


def get_shift_label_for_date(session: Session, employee_id: int, selected_day: date) -> str:
    shift_period = session.scalar(
        select(EmployeeShiftPeriod)
        .join(Period, Period.id == EmployeeShiftPeriod.period_id)
        .where(
            EmployeeShiftPeriod.employee_id == employee_id,
            Period.start_date <= selected_day,
            Period.end_date >= selected_day,
        )
    )
    if shift_period is None:
        return "-"
    return "Ca ngày" if shift_period.shift.value == "day" else "Ca đêm"


def build_attendance_status_map(session: Session, selected_day: date) -> dict[int, str]:
    records = session.scalars(select(DailyRecord).where(DailyRecord.date == selected_day)).all()
    return {record.employee_id: attendance_status_from_record(record) for record in records}


def save_attendance(
    session: Session,
    employee_id: int,
    selected_day: date,
    team: Team,
    blow_payload: dict[int, int | None],
    cut_payload: list[tuple[int, int]],
    *,
    is_absent: bool,
    mark_done: bool,
) -> AttendanceSaveResult:
    ensure_period_for_date(session, selected_day)
    record = get_or_create_daily_record(session, employee_id, selected_day)
    if record.status == DailyRecordStatus.DONE:
        record.status = DailyRecordStatus.DRAFT
        session.flush()

    record.work_logs.clear()
    record.cut_logs.clear()
    session.flush()

    if is_absent:
        set_daily_record_absent(session, record.id, True)
    else:
        set_daily_record_absent(session, record.id, False)
        if team == Team.BLOW:
            for work_type_id, quantity in blow_payload.items():
                add_blow_work(session, record.id, work_type_id, quantity)
        else:
            for bag_type_id, quantity in cut_payload:
                add_cut_work(session, record.id, bag_type_id, quantity)

    record.status = DailyRecordStatus.DONE if mark_done else DailyRecordStatus.DRAFT
    session.flush()
    session.commit()
    return AttendanceSaveResult(
        record_id=record.id,
        status=record.status,
        is_absent=record.is_absent,
    )


def attendance_status_from_record(record: DailyRecord) -> str:
    if record.is_absent:
        return "Nghỉ"
    if record.status == DailyRecordStatus.DONE:
        return "Đã lưu"
    return "Nháp"


def _calculate_cycle_bounds(current_day: date) -> tuple[date, date]:
    if current_day.day <= 10:
        start_day = 1
        end_day = 10
    elif current_day.day <= 20:
        start_day = 11
        end_day = 20
    else:
        start_day = 21
        end_day = calendar.monthrange(current_day.year, current_day.month)[1]
    return date(current_day.year, current_day.month, start_day), date(current_day.year, current_day.month, end_day)
