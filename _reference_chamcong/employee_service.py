from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from models import DailyRecord
from models import Employee
from models import Team
from services import NotFoundError
from services import ValidationError


@dataclass(frozen=True)
class EmployeeDeleteResult:
    employee_id: int
    employee_name: str
    deleted_without_history: bool


def list_employees(session: Session) -> list[Employee]:
    return session.scalars(select(Employee).order_by(Employee.team, Employee.name)).all()


def create_employee(session: Session, name: str, team: Team, is_active: bool) -> Employee:
    normalized_name = _normalize_employee_name(name)
    if _employee_name_exists(session, normalized_name):
        raise ValidationError("employee name already exists")

    employee = Employee(name=normalized_name, team=team, is_active=is_active)
    session.add(employee)
    session.commit()
    return employee


def update_employee(session: Session, employee_id: int, name: str, team: Team, is_active: bool) -> Employee:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("employee not found")

    normalized_name = _normalize_employee_name(name)
    if _employee_name_exists(session, normalized_name, exclude_employee_id=employee_id):
        raise ValidationError("employee name already exists")

    employee.name = normalized_name
    employee.team = team
    employee.is_active = is_active
    session.commit()
    return employee


def delete_or_deactivate_employee(session: Session, employee_id: int) -> EmployeeDeleteResult:
    employee = session.get(Employee, employee_id)
    if employee is None:
        raise NotFoundError("employee not found")

    employee_name = employee.name
    has_history = session.scalar(
        select(DailyRecord.id).where(DailyRecord.employee_id == employee_id).limit(1)
    )
    if has_history is None:
        session.delete(employee)
        session.commit()
        return EmployeeDeleteResult(
            employee_id=employee_id,
            employee_name=employee_name,
            deleted_without_history=True,
        )

    employee.is_active = False
    session.commit()
    return EmployeeDeleteResult(
        employee_id=employee_id,
        employee_name=employee_name,
        deleted_without_history=False,
    )


def _normalize_employee_name(name: str) -> str:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValidationError("employee name is required")
    return normalized_name


def _employee_name_exists(
    session: Session, name: str, *, exclude_employee_id: int | None = None
) -> bool:
    query = select(Employee.id).where(Employee.name == name)
    if exclude_employee_id is not None:
        query = query.where(Employee.id != exclude_employee_id)
    return session.scalar(query.limit(1)) is not None
