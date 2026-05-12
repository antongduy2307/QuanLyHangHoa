from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from core.exceptions import NotFoundError
from modules.attendance.db import AttendanceSessionLocal
from modules.attendance.models import BagType, CutLog, DailyRecord, Employee, ExtraCutWorkLog, Period, Team, WorkLog, WorkType


class AttendanceEmployeeRepository:
    def __init__(self, session_factory: sessionmaker[Session] = AttendanceSessionLocal) -> None:
        self._session_factory = session_factory

    def session(self) -> Session:
        return self._session_factory()

    def list_employees(
        self,
        session: Session,
        *,
        search_text: str = "",
        include_inactive: bool = False,
    ) -> Sequence[Employee]:
        statement = select(Employee).order_by(Employee.team.asc(), Employee.name.asc())
        if not include_inactive:
            statement = statement.where(Employee.is_active.is_(True))
        if search_text:
            statement = statement.where(Employee.name.ilike(f"%{search_text}%"))
        return session.scalars(statement).all()

    def get_employee(self, session: Session, employee_id: int) -> Employee:
        employee = session.get(Employee, employee_id)
        if employee is None:
            raise NotFoundError("employee not found")
        return employee

    def employee_name_exists(
        self,
        session: Session,
        name: str,
        *,
        exclude_employee_id: int | None = None,
    ) -> bool:
        statement = select(Employee.id).where(Employee.name == name)
        if exclude_employee_id is not None:
            statement = statement.where(Employee.id != exclude_employee_id)
        return session.scalar(statement.limit(1)) is not None

    def create_employee(self, session: Session, *, name: str, team: Team, is_active: bool) -> Employee:
        employee = Employee(name=name, team=team, is_active=is_active)
        session.add(employee)
        session.flush()
        return employee

    def update_employee(
        self,
        session: Session,
        employee: Employee,
        *,
        name: str,
        team: Team,
        is_active: bool,
    ) -> Employee:
        employee.name = name
        employee.team = team
        employee.is_active = is_active
        session.flush()
        return employee

    def count_daily_records(self, session: Session, employee_id: int) -> int:
        count = session.scalar(
            select(func.count(DailyRecord.id)).where(DailyRecord.employee_id == employee_id)
        )
        return int(count or 0)

    def delete_employee(self, session: Session, employee: Employee) -> None:
        session.delete(employee)
        session.flush()


class AttendanceDayEntryRepository:
    def __init__(self, session_factory: sessionmaker[Session] = AttendanceSessionLocal) -> None:
        self._session_factory = session_factory

    def session(self) -> Session:
        return self._session_factory()

    def list_active_employees(self, session: Session) -> Sequence[Employee]:
        return session.scalars(
            select(Employee)
            .where(Employee.is_active.is_(True))
            .order_by(Employee.team.asc(), Employee.name.asc())
        ).all()

    def get_employee(self, session: Session, employee_id: int) -> Employee:
        employee = session.get(Employee, employee_id)
        if employee is None:
            raise NotFoundError("employee not found")
        return employee

    def get_period_for_date(self, session: Session, selected_date) -> Period | None:
        return session.scalar(
            select(Period).where(
                Period.start_date <= selected_date,
                Period.end_date >= selected_date,
            )
        )

    def create_period(self, session: Session, *, start_date, end_date) -> Period:
        period = Period(start_date=start_date, end_date=end_date)
        session.add(period)
        session.flush()
        return period

    def get_daily_record(self, session: Session, employee_id: int, selected_date) -> DailyRecord | None:
        return session.scalar(
            select(DailyRecord)
            .options(
                selectinload(DailyRecord.employee),
                selectinload(DailyRecord.period),
                selectinload(DailyRecord.work_logs).selectinload(WorkLog.work_type),
                selectinload(DailyRecord.cut_logs).selectinload(CutLog.bag_type),
                selectinload(DailyRecord.extra_cut_work_logs).selectinload(ExtraCutWorkLog.bag_type),
            )
            .where(
                DailyRecord.employee_id == employee_id,
                DailyRecord.date == selected_date,
            )
        )

    def list_daily_records_for_date(self, session: Session, selected_date) -> Sequence[DailyRecord]:
        return session.scalars(select(DailyRecord).where(DailyRecord.date == selected_date)).all()

    def create_daily_record(
        self,
        session: Session,
        *,
        employee_id: int,
        selected_date,
        period_id: int,
    ) -> DailyRecord:
        record = DailyRecord(
            employee_id=employee_id,
            date=selected_date,
            period_id=period_id,
        )
        session.add(record)
        session.flush()
        return record

    def list_work_types_for_entry(self, session: Session, include_ids: set[int] | None = None) -> Sequence[WorkType]:
        include_ids = include_ids or set()
        statement = (
            select(WorkType)
            .where((WorkType.is_active.is_(True)) | (WorkType.id.in_(include_ids)))
            .order_by(WorkType.id.asc())
        )
        return session.scalars(statement).all()

    def list_bag_types_for_entry(self, session: Session, include_ids: set[int] | None = None) -> Sequence[BagType]:
        include_ids = include_ids or set()
        available_condition = (
            (BagType.is_active.is_(True))
            & (BagType.is_product_linked.is_(True))
            & (BagType.is_excluded_from_attendance.is_(False))
            & (BagType.is_legacy.is_(False))
            & (BagType.quota_quantity > 0)
            & (BagType.excess_unit_price > 0)
        )
        statement = (
            select(BagType)
            .where(available_condition | (BagType.id.in_(include_ids)))
            .order_by(BagType.id.asc())
        )
        return session.scalars(statement).all()

    def get_work_type(self, session: Session, work_type_id: int) -> WorkType:
        work_type = session.get(WorkType, work_type_id)
        if work_type is None:
            raise NotFoundError("work type not found")
        return work_type

    def get_bag_type(self, session: Session, bag_type_id: int) -> BagType:
        bag_type = session.get(BagType, bag_type_id)
        if bag_type is None:
            raise NotFoundError("bag type not found")
        return bag_type
