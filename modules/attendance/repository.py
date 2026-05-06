from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from core.exceptions import NotFoundError
from modules.attendance.db import AttendanceSessionLocal
from modules.attendance.models import DailyRecord, Employee, Team


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
