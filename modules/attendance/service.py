from __future__ import annotations

import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session, sessionmaker

from core.exceptions import NotFoundError, ValidationError
from modules.attendance.blow_work import calculate_blow_work_amount
from modules.attendance.cut_bonus import CutBonusItem, calculate_cut_employee_bonus
from modules.attendance.db import AttendanceSessionLocal
from modules.attendance.dto import (
    AttendanceEmployeeRow,
    AttendanceSavePayload,
    AttendanceSaveResult,
    BagTypeOption,
    CutLogValue,
    DayEntryDTO,
    ExtraCutWorkLogValue,
    WorkLogValue,
    WorkTypeOption,
)
from modules.attendance.models import CutLog, DailyRecord, DailyRecordStatus, Employee, ExtraCutWorkLog, Team, WorkInputType, WorkLog
from modules.attendance.repository import AttendanceDayEntryRepository, AttendanceEmployeeRepository


@dataclass(frozen=True, slots=True)
class EmployeeDeleteResult:
    employee_id: int
    employee_name: str
    deleted_without_history: bool


class AttendanceEmployeeService:
    def __init__(
        self,
        repository: AttendanceEmployeeRepository | None = None,
        session_factory: sessionmaker[Session] = AttendanceSessionLocal,
    ) -> None:
        self._session_factory = session_factory
        self._repository = repository or AttendanceEmployeeRepository(session_factory)

    def list_employees(self, *, search_text: str = "", include_inactive: bool = False) -> Sequence[Employee]:
        with self._session_factory() as session:
            return self._repository.list_employees(
                session,
                search_text=search_text.strip(),
                include_inactive=include_inactive,
            )

    def get_employee(self, employee_id: int) -> Employee:
        with self._session_factory() as session:
            return self._repository.get_employee(session, employee_id)

    def create_employee(self, *, name: str, team: Team | str, is_active: bool = True) -> Employee:
        normalized_name = self._normalize_employee_name(name)
        normalized_team = self._coerce_team(team)
        with self._session_factory() as session:
            with session.begin():
                if self._repository.employee_name_exists(session, normalized_name):
                    raise ValidationError("employee name already exists")
                return self._repository.create_employee(
                    session,
                    name=normalized_name,
                    team=normalized_team,
                    is_active=is_active,
                )

    def update_employee(self, employee_id: int, *, name: str, team: Team | str, is_active: bool) -> Employee:
        normalized_name = self._normalize_employee_name(name)
        normalized_team = self._coerce_team(team)
        with self._session_factory() as session:
            with session.begin():
                employee = self._repository.get_employee(session, employee_id)
                if self._repository.employee_name_exists(
                    session,
                    normalized_name,
                    exclude_employee_id=employee_id,
                ):
                    raise ValidationError("employee name already exists")
                return self._repository.update_employee(
                    session,
                    employee,
                    name=normalized_name,
                    team=normalized_team,
                    is_active=is_active,
                )

    def delete_or_deactivate_employee(self, employee_id: int) -> EmployeeDeleteResult:
        with self._session_factory() as session:
            with session.begin():
                employee = self._repository.get_employee(session, employee_id)
                employee_name = employee.name
                if self._repository.count_daily_records(session, employee_id) == 0:
                    self._repository.delete_employee(session, employee)
                    return EmployeeDeleteResult(
                        employee_id=employee_id,
                        employee_name=employee_name,
                        deleted_without_history=True,
                    )

                employee.is_active = False
                session.flush()
                return EmployeeDeleteResult(
                    employee_id=employee_id,
                    employee_name=employee_name,
                    deleted_without_history=False,
                )

    def _normalize_employee_name(self, name: str) -> str:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValidationError("employee name is required")
        return normalized_name

    def _coerce_team(self, team: Team | str) -> Team:
        if isinstance(team, Team):
            return team
        try:
            return Team(team)
        except ValueError as exc:
            raise ValidationError("invalid team") from exc


GLOVE_WORK_NAMES = {"Phụ găng 1 máy", "Phụ găng 2 máy"}


class AttendanceDayEntryService:
    def __init__(
        self,
        repository: AttendanceDayEntryRepository | None = None,
        session_factory: sessionmaker[Session] = AttendanceSessionLocal,
    ) -> None:
        self._session_factory = session_factory
        self._repository = repository or AttendanceDayEntryRepository(session_factory)

    def period_bounds_for_date(self, selected_date: date) -> tuple[date, date]:
        if selected_date.day <= 10:
            return selected_date.replace(day=1), selected_date.replace(day=10)
        if selected_date.day <= 20:
            return selected_date.replace(day=11), selected_date.replace(day=20)
        return (
            selected_date.replace(day=21),
            selected_date.replace(day=calendar.monthrange(selected_date.year, selected_date.month)[1]),
        )

    def ensure_period_for_date(self, selected_date: date):
        with self._session_factory() as session:
            with session.begin():
                return self._ensure_period_for_date(session, selected_date)

    def list_attendance_employees_for_date(self, selected_date: date) -> list[AttendanceEmployeeRow]:
        with self._session_factory() as session:
            employees = self._repository.list_active_employees(session)
            records = self._repository.list_daily_records_for_date(session, selected_date)
            status_by_employee_id = {
                record.employee_id: self.attendance_status_from_record(record)
                for record in records
            }
            return [
                AttendanceEmployeeRow(
                    id=employee.id,
                    name=employee.name,
                    team=employee.team,
                    status_label=status_by_employee_id.get(employee.id, "Chưa chấm"),
                )
                for employee in employees
            ]

    def get_daily_record(self, employee_id: int, selected_date: date) -> DailyRecord | None:
        with self._session_factory() as session:
            return self._repository.get_daily_record(session, employee_id, selected_date)

    def get_day_entry(self, employee_id: int, selected_date: date) -> DayEntryDTO:
        with self._session_factory() as session:
            employee = self._repository.get_employee(session, employee_id)
            record = self._repository.get_daily_record(session, employee_id, selected_date)
            work_logs = list(record.work_logs) if record is not None else []
            cut_logs = list(record.cut_logs) if record is not None else []
            extra_cut_work_logs = list(record.extra_cut_work_logs) if record is not None else []
            work_type_ids = {log.work_type_id for log in work_logs}
            bag_type_ids = {log.bag_type_id for log in cut_logs}
            bag_type_ids.update(log.bag_type_id for log in extra_cut_work_logs)
            work_types = self._repository.list_work_types_for_entry(session, work_type_ids)
            bag_types = self._repository.list_bag_types_for_entry(session, bag_type_ids)
            return DayEntryDTO(
                employee_id=employee.id,
                employee_name=employee.name,
                team=employee.team,
                selected_date=selected_date,
                status_label="Chưa chấm" if record is None else self.attendance_status_from_record(record),
                record_status=None if record is None else record.status,
                is_absent=False if record is None else record.is_absent,
                total_amount_snapshot=0 if record is None else record.total_amount_snapshot,
                work_types=[
                    WorkTypeOption(
                        id=work_type.id,
                        name=work_type.name,
                        input_type=work_type.input_type,
                        unit_price=work_type.unit_price,
                        is_active=work_type.is_active,
                    )
                    for work_type in work_types
                ],
                bag_types=[
                    BagTypeOption(
                        id=bag_type.id,
                        name=bag_type.name,
                        quota_quantity=bag_type.quota_quantity,
                        excess_unit_price=bag_type.excess_unit_price,
                        is_active=bag_type.is_active,
                    )
                    for bag_type in bag_types
                ],
                work_logs=[
                    WorkLogValue(
                        work_type_id=log.work_type_id,
                        quantity=log.quantity,
                        unit_price_snapshot=log.unit_price_snapshot,
                        amount_snapshot=log.amount_snapshot,
                    )
                    for log in work_logs
                ],
                cut_logs=[
                    CutLogValue(
                        bag_type_id=log.bag_type_id,
                        quantity=log.quantity,
                        unit_price_snapshot=log.unit_price_snapshot,
                        quota_quantity_snapshot=log.quota_quantity_snapshot,
                        excess_unit_price_snapshot=log.excess_unit_price_snapshot,
                        amount_snapshot=log.amount_snapshot,
                    )
                    for log in cut_logs
                ],
                extra_cut_work_logs=[
                    ExtraCutWorkLogValue(
                        bag_type_id=log.bag_type_id,
                        quantity=log.quantity,
                        excess_unit_price_snapshot=log.excess_unit_price_snapshot,
                        amount_snapshot=log.amount_snapshot,
                    )
                    for log in extra_cut_work_logs
                ],
            )

    def save_attendance(self, payload: AttendanceSavePayload, *, finalize: bool) -> AttendanceSaveResult:
        with self._session_factory() as session:
            with session.begin():
                employee = self._repository.get_employee(session, payload.employee_id)
                if not employee.is_active:
                    raise ValidationError("employee is inactive")

                period = self._ensure_period_for_date(session, payload.selected_date)
                record = self._repository.get_daily_record(session, employee.id, payload.selected_date)
                if record is None:
                    record = self._repository.create_daily_record(
                        session,
                        employee_id=employee.id,
                        selected_date=payload.selected_date,
                        period_id=period.id,
                    )
                    record.employee = employee
                    record.period = period
                elif record.period.locked:
                    raise ValidationError("cannot modify daily record in a locked period")

                record.status = DailyRecordStatus.DRAFT
                record.work_logs.clear()
                record.cut_logs.clear()
                record.extra_cut_work_logs.clear()
                session.flush()

                if payload.is_absent:
                    record.is_absent = True
                    record.total_amount_snapshot = 0
                else:
                    record.is_absent = False
                    if employee.team == Team.BLOW:
                        self._apply_blow_payload(session, record, payload)
                    elif employee.team == Team.CUT:
                        self._apply_cut_payload(session, record, payload)
                    else:
                        raise ValidationError("invalid employee team")

                if employee.team != Team.CUT:
                    record.total_amount_snapshot = self._calculate_daily_total(record)
                if payload.is_absent:
                    record.total_amount_snapshot = 0
                record.status = DailyRecordStatus.DONE if finalize else DailyRecordStatus.DRAFT
                session.flush()
                return AttendanceSaveResult(
                    record_id=record.id,
                    status=record.status,
                    is_absent=record.is_absent,
                    total_amount_snapshot=record.total_amount_snapshot,
                )

    def record_status_label(self, employee_id: int, selected_date: date) -> str:
        with self._session_factory() as session:
            record = self._repository.get_daily_record(session, employee_id, selected_date)
            if record is None:
                return "Chưa chấm"
            return self.attendance_status_from_record(record)

    def attendance_status_from_record(self, record: DailyRecord) -> str:
        if record.is_absent:
            return "Nghỉ"
        if record.status == DailyRecordStatus.DONE:
            return "Đã lưu"
        return "Nháp"

    def _ensure_period_for_date(self, session: Session, selected_date: date):
        period = self._repository.get_period_for_date(session, selected_date)
        if period is not None:
            return period
        start_date, end_date = self.period_bounds_for_date(selected_date)
        return self._repository.create_period(session, start_date=start_date, end_date=end_date)

    def _apply_blow_payload(self, session: Session, record: DailyRecord, payload: AttendanceSavePayload) -> None:
        if payload.cut_work:
            raise ValidationError("cut payload is invalid for blow team")

        seen_work_type_ids: set[int] = set()
        selected_glove_names: set[str] = set()
        for item in payload.blow_work:
            if item.work_type_id in seen_work_type_ids:
                raise ValidationError("duplicate work type")
            seen_work_type_ids.add(item.work_type_id)

            work_type = self._repository.get_work_type(session, item.work_type_id)
            if not work_type.is_active:
                raise ValidationError("work type is inactive")
            if work_type.team != Team.BLOW:
                raise ValidationError("work type must belong to blow team")
            if work_type.name in GLOVE_WORK_NAMES:
                selected_glove_names.add(work_type.name)

            quantity = self._resolve_work_quantity(work_type.input_type, item.quantity)
            if quantity == 0:
                continue
            amount = calculate_blow_work_amount(work_type.input_type, quantity, work_type.unit_price, work_type.name)
            record.work_logs.append(
                WorkLog(
                    work_type_id=work_type.id,
                    quantity=quantity,
                    unit_price_snapshot=work_type.unit_price,
                    amount_snapshot=amount,
                )
            )

        if len(selected_glove_names) > 1:
            raise ValidationError("cannot use both glove work types in the same daily record")
        self._apply_extra_cut_work_payload(session, record, payload)

    def _apply_cut_payload(self, session: Session, record: DailyRecord, payload: AttendanceSavePayload) -> None:
        if payload.blow_work:
            raise ValidationError("blow payload is invalid for cut team")
        if payload.extra_cut_work:
            raise ValidationError("extra cut payload is invalid for cut team")

        merged_quantities: dict[int, Decimal] = {}
        for item in payload.cut_work:
            quantity = self._quantity_to_decimal(item.quantity)
            if quantity < 0:
                raise ValidationError("quantity must be non-negative")
            if quantity == 0:
                continue
            merged_quantities[item.bag_type_id] = merged_quantities.get(item.bag_type_id, Decimal("0")) + quantity

        active_items: list[tuple[int, Decimal, Decimal, Decimal, int]] = []
        for bag_type_id, quantity in merged_quantities.items():
            bag_type = self._repository.get_bag_type(session, bag_type_id)
            if not bag_type.is_active:
                raise ValidationError("bag type is inactive")
            quota_quantity = Decimal(str(bag_type.quota_quantity))
            excess_unit_price = Decimal(str(bag_type.excess_unit_price))
            active_items.append((bag_type.id, quantity, quota_quantity, excess_unit_price, bag_type.unit_price))

        if not active_items:
            record.total_amount_snapshot = 0
            return

        total_amount = calculate_cut_employee_bonus(
            CutBonusItem(quantity=quantity, quota_quantity=quota_quantity, excess_unit_price=excess_unit_price)
            for _bag_type_id, quantity, quota_quantity, excess_unit_price, _legacy_price in active_items
        )
        record.total_amount_snapshot = self._decimal_money_to_int(total_amount)

        for bag_type_id, quantity, quota_quantity, excess_unit_price, legacy_unit_price in active_items:
            record.cut_logs.append(
                CutLog(
                    bag_type_id=bag_type_id,
                    quantity=quantity,
                    unit_price_snapshot=legacy_unit_price,
                    quota_quantity_snapshot=quota_quantity,
                    excess_unit_price_snapshot=excess_unit_price,
                    amount_snapshot=0,
                )
            )

    def _resolve_work_quantity(self, input_type: WorkInputType, quantity: int | None) -> int:
        if input_type == WorkInputType.TICK:
            return 1
        if input_type == WorkInputType.QUANTITY:
            if quantity is None:
                raise ValidationError("quantity is required for quantity work type")
            if quantity < 0:
                raise ValidationError("quantity must be non-negative")
            return quantity
        raise ValidationError("unsupported work input type")

    def _calculate_daily_total(self, record: DailyRecord) -> int:
        return (
            sum(log.amount_snapshot for log in record.work_logs)
            + sum(log.amount_snapshot for log in record.cut_logs)
            + sum(log.amount_snapshot for log in record.extra_cut_work_logs)
        )

    def _apply_extra_cut_work_payload(self, session: Session, record: DailyRecord, payload: AttendanceSavePayload) -> None:
        merged_quantities: dict[int, Decimal] = {}
        for item in payload.extra_cut_work:
            quantity = self._quantity_to_decimal(item.quantity)
            if quantity < 0:
                raise ValidationError("quantity must be non-negative")
            if quantity == 0:
                continue
            merged_quantities[item.bag_type_id] = merged_quantities.get(item.bag_type_id, Decimal("0")) + quantity

        for bag_type_id, quantity in merged_quantities.items():
            bag_type = self._repository.get_bag_type(session, bag_type_id)
            if not bag_type.is_active:
                raise ValidationError("bag type is inactive")
            excess_unit_price = Decimal(str(bag_type.excess_unit_price))
            amount = self._decimal_money_to_int(quantity * excess_unit_price)
            record.extra_cut_work_logs.append(
                ExtraCutWorkLog(
                    bag_type_id=bag_type.id,
                    quantity=quantity,
                    excess_unit_price_snapshot=excess_unit_price,
                    amount_snapshot=amount,
                )
            )

    def _decimal_money_to_int(self, value: Decimal) -> int:
        return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    def _quantity_to_decimal(self, value: Decimal | int | str) -> Decimal:
        try:
            return Decimal(str(value))
        except Exception as exc:
            raise ValidationError("quantity must be numeric") from exc
