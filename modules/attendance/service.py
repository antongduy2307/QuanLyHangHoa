from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker

from core.exceptions import NotFoundError, ValidationError
from modules.attendance.db import AttendanceSessionLocal
from modules.attendance.models import Employee, Team
from modules.attendance.repository import AttendanceEmployeeRepository


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
