from __future__ import annotations

from datetime import date

from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy.orm import Session

from models import BagType
from models import CutLog
from models import DailyRecord
from models import DailyRecordStatus
from models import Employee
from models import EmployeeShiftPeriod
from models import Period
from models import Shift
from models import Team
from models import WorkInputType
from models import WorkLog
from models import WorkType


class ServiceError(Exception):
    """Base exception for service-layer errors."""


class NotFoundError(ServiceError):
    """Raised when a required record does not exist."""


class ValidationError(ServiceError):
    """Raised when input data or state is invalid."""


class LockedPeriodError(ServiceError):
    """Raised when attempting to modify a locked period."""


def create_period(session: Session, start_date: date, end_date: date) -> Period:
    """Create a new payroll period when it does not overlap an existing one."""
    if start_date > end_date:
        raise ValidationError("start_date must be on or before end_date")

    overlap_stmt = select(Period).where(
        Period.start_date <= end_date,
        Period.end_date >= start_date,
    )
    overlap = session.scalar(overlap_stmt)
    if overlap is not None:
        raise ValidationError("period overlaps with an existing period")

    period = Period(start_date=start_date, end_date=end_date)
    session.add(period)
    session.flush()
    return period


def assign_shift(session: Session, employee_id: int, period_id: int, shift: Shift | str) -> EmployeeShiftPeriod:
    """Assign one shift to an employee for a period unless the period is locked."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("employee not found")
    if not employee.is_active:
        raise ValidationError("employee is inactive")

    period = session.get(Period, period_id)
    if period is None:
        raise NotFoundError("period not found")
    if period.locked:
        raise LockedPeriodError("cannot change shift for a locked period")

    shift_value = _coerce_shift(shift)

    stmt = select(EmployeeShiftPeriod).where(
        EmployeeShiftPeriod.employee_id == employee_id,
        EmployeeShiftPeriod.period_id == period_id,
    )
    assignment = session.scalar(stmt)
    if assignment is not None:
        raise ValidationError("shift already assigned for this period")

    assignment = EmployeeShiftPeriod(
        employee_id=employee_id,
        period_id=period_id,
        shift=shift_value,
    )
    session.add(assignment)

    session.flush()
    return assignment


def get_or_create_daily_record(session: Session, employee_id: int, day: date) -> DailyRecord:
    """Fetch an existing daily record or create one inside the matching period."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("employee not found")
    if not employee.is_active:
        raise ValidationError("employee is inactive")

    stmt = select(DailyRecord).where(
        DailyRecord.employee_id == employee_id,
        DailyRecord.date == day,
    )
    record = session.scalar(stmt)
    if record is not None:
        return record

    period = _get_period_for_date(session, day)
    if period.locked:
        raise LockedPeriodError("cannot create record in locked period")
    record = DailyRecord(
        employee_id=employee_id,
        date=day,
        period_id=period.id,
        status=DailyRecordStatus.DRAFT,
        total_amount_snapshot=0,
    )
    session.add(record)
    session.flush()
    return record


def add_blow_work(
    session: Session,
    daily_record_id: int,
    work_type_id: int,
    quantity: int | None = None,
) -> WorkLog:
    """Add or update one blow-team work log and refresh the daily total."""
    record = _get_daily_record_with_employee(session, daily_record_id)
    _ensure_daily_record_editable(record)
    _ensure_daily_record_is_not_absent(record)
    if not record.employee.is_active:
        raise ValidationError("employee is inactive")
    if record.employee.team != Team.BLOW:
        raise ValidationError("daily record employee is not in blow team")

    work_type = session.get(WorkType, work_type_id)
    if work_type is None:
        raise NotFoundError("work type not found")
    if work_type.team != Team.BLOW:
        raise ValidationError("work type must belong to blow team")
    if not work_type.is_active:
        raise ValidationError("work type is inactive")

    stored_quantity = _resolve_work_quantity(work_type, quantity)
    _ensure_glove_work_is_exclusive(session, daily_record_id, work_type)
    unit_price_snapshot = work_type.unit_price
    amount_snapshot = stored_quantity * unit_price_snapshot

    stmt = select(WorkLog).where(
        WorkLog.daily_record_id == daily_record_id,
        WorkLog.work_type_id == work_type_id,
    )
    work_log = session.scalar(stmt)

    if work_log is None:
        work_log = WorkLog(
            daily_record_id=daily_record_id,
            work_type_id=work_type_id,
            quantity=stored_quantity,
            unit_price_snapshot=unit_price_snapshot,
            amount_snapshot=amount_snapshot,
        )
        session.add(work_log)
    else:
        work_log.quantity = stored_quantity
        work_log.unit_price_snapshot = unit_price_snapshot
        work_log.amount_snapshot = amount_snapshot

    session.flush()
    _recalculate_daily_total(record)
    session.flush()
    return work_log


def add_cut_work(session: Session, daily_record_id: int, bag_type_id: int, quantity: int) -> CutLog:
    """Add or update a cut-team bag row and refresh the daily total."""
    record = _get_daily_record_with_employee(session, daily_record_id)
    _ensure_daily_record_editable(record)
    _ensure_daily_record_is_not_absent(record)
    if not record.employee.is_active:
        raise ValidationError("employee is inactive")
    if record.employee.team != Team.CUT:
        raise ValidationError("daily record employee is not in cut team")

    if quantity < 0:
        raise ValidationError("quantity must be non-negative")

    bag_type = session.get(BagType, bag_type_id)
    if bag_type is None:
        raise NotFoundError("bag type not found")
    if not bag_type.is_active:
        raise ValidationError("bag type is inactive")

    stmt = select(CutLog).where(
        CutLog.daily_record_id == daily_record_id,
        CutLog.bag_type_id == bag_type_id,
    )
    cut_log = session.scalar(stmt)
    unit_price = bag_type.unit_price

    if cut_log is None:
        cut_log = CutLog(
            daily_record_id=daily_record_id,
            bag_type_id=bag_type_id,
            quantity=quantity,
            unit_price_snapshot=unit_price,
            amount_snapshot=quantity * unit_price,
        )
        session.add(cut_log)
    else:
        cut_log.quantity = quantity
        cut_log.unit_price_snapshot = unit_price
        cut_log.amount_snapshot = quantity * unit_price

    session.flush()
    _recalculate_daily_total(record)
    session.flush()
    return cut_log


def finalize_daily_record(session: Session, daily_record_id: int) -> DailyRecord:
    """Validate a daily record and mark it as done."""
    record = _get_daily_record_with_employee(session, daily_record_id)
    _ensure_daily_record_editable(record)
    if record.is_absent:
        record.total_amount_snapshot = 0
    _validate_daily_record(record)
    record.status = DailyRecordStatus.DONE
    session.flush()
    return record


def set_daily_record_absent(session: Session, daily_record_id: int, is_absent: bool) -> DailyRecord:
    """Toggle absent status for a draft daily record."""
    record = _get_daily_record_with_employee(session, daily_record_id)
    _ensure_daily_record_editable(record)
    if not record.employee.is_active:
        raise ValidationError("employee is inactive")

    if is_absent:
        record.work_logs.clear()
        record.cut_logs.clear()
        record.total_amount_snapshot = 0
    else:
        _recalculate_daily_total(record)

    record.is_absent = is_absent
    session.flush()
    return record


def calculate_period_total(session: Session, employee_id: int, period_id: int) -> int:
    """Return the total snapped amount for all daily records of an employee in a period."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("employee not found")

    period = session.get(Period, period_id)
    if period is None:
        raise NotFoundError("period not found")

    stmt = select(func.coalesce(func.sum(DailyRecord.total_amount_snapshot), 0)).where(
        DailyRecord.employee_id == employee_id,
        DailyRecord.period_id == period_id,
    )
    total = session.scalar(stmt)
    return int(total or 0)


def calculate_kpi(session: Session, employee_id: int, month: int, year: int) -> int:
    """Calculate monthly KPI for a blow-team employee."""
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("employee not found")
    if employee.team != Team.BLOW:
        raise ValidationError("kpi is only available for blow team employees")
    if month < 1 or month > 12:
        raise ValidationError("month must be between 1 and 12")

    stmt = select(func.count(DailyRecord.id)).where(
        DailyRecord.employee_id == employee_id,
        DailyRecord.status == DailyRecordStatus.DONE,
        DailyRecord.total_amount_snapshot > 0,
        func.strftime("%m", DailyRecord.date) == f"{month:02d}",
        func.strftime("%Y", DailyRecord.date) == f"{year:04d}",
    )
    days = int(session.scalar(stmt) or 0)
    if days < 26:
        return 0

    bonus_rate = (days - 26) * 5000
    return 600000 + bonus_rate * days


def _get_period_for_date(session: Session, day: date) -> Period:
    stmt = select(Period).where(
        Period.start_date <= day,
        Period.end_date >= day,
    )
    period = session.scalar(stmt)
    if period is None:
        raise ValidationError("no period found for date")
    return period


def _get_daily_record_with_employee(session: Session, daily_record_id: int) -> DailyRecord:
    record = session.get(DailyRecord, daily_record_id)
    if record is None:
        raise NotFoundError("daily record not found")

    employee = record.employee
    if employee is None:
        raise ValidationError("daily record has no employee")
    return record


def _ensure_daily_record_editable(record: DailyRecord) -> None:
    if record.period.locked:
        raise LockedPeriodError("cannot modify daily record in a locked period")
    if record.status == DailyRecordStatus.DONE:
        raise ValidationError("cannot modify a finalized daily record")


def _ensure_daily_record_is_not_absent(record: DailyRecord) -> None:
    if record.is_absent:
        raise ValidationError("Cannot add work to absent record")


def _validate_daily_record(record: DailyRecord) -> None:
    if record.is_absent:
        record.total_amount_snapshot = 0
        return

    if record.employee.team == Team.BLOW and not record.work_logs:
        raise ValidationError("blow team daily record must contain at least one work log")
    if record.employee.team == Team.CUT and not record.cut_logs:
        raise ValidationError("cut team daily record must contain at least one cut log")

    computed_total = _calculate_daily_total(record)
    if computed_total != record.total_amount_snapshot:
        record.total_amount_snapshot = computed_total

    if record.total_amount_snapshot < 0:
        raise ValidationError("daily total cannot be negative")


def _recalculate_daily_total(record: DailyRecord) -> None:
    record.total_amount_snapshot = _calculate_daily_total(record)


def _calculate_daily_total(record: DailyRecord) -> int:
    work_total = sum(log.amount_snapshot for log in record.work_logs)
    cut_total = sum(log.amount_snapshot for log in record.cut_logs)
    return work_total + cut_total


def _coerce_shift(shift: Shift | str) -> Shift:
    if isinstance(shift, Shift):
        return shift
    try:
        return Shift(shift)
    except ValueError as exc:
        raise ValidationError("invalid shift value") from exc


def _resolve_work_quantity(work_type: WorkType, quantity: int | None) -> int:
    if work_type.input_type == WorkInputType.TICK:
        return 1
    if work_type.input_type == WorkInputType.QUANTITY:
        if quantity is None:
            raise ValidationError("quantity is required for quantity work type")
        if quantity <= 0:
            raise ValidationError("quantity must be greater than zero")
        return quantity
    raise ValidationError("unsupported work input type")


def _ensure_glove_work_is_exclusive(session: Session, daily_record_id: int, work_type: WorkType) -> None:
    glove_names = {"Phụ găng 1 máy", "Phụ găng 2 máy"}
    if work_type.name not in glove_names:
        return

    stmt = (
        select(WorkLog)
        .join(WorkType, WorkType.id == WorkLog.work_type_id)
        .where(
            WorkLog.daily_record_id == daily_record_id,
            WorkType.name.in_(glove_names - {work_type.name}),
        )
    )
    conflicting_work_log = session.scalar(stmt)
    if conflicting_work_log is not None:
        raise ValidationError("cannot use both glove work types in the same daily record")
