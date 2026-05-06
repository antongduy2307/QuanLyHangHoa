from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from core.exceptions import NotFoundError, ValidationError
from modules.attendance.db import AttendanceSessionLocal
from modules.attendance.models import BagType, CutLog, DailyRecord, Employee, Team, WorkInputType, WorkLog, WorkType


@dataclass(frozen=True, slots=True)
class ReportPeriodOption:
    id: int
    label: str
    start_date: date
    end_date: date


@dataclass(frozen=True, slots=True)
class ReportColumn:
    kind: str
    label: str
    employee_id: int | None = None
    employee_name: str | None = None


@dataclass(frozen=True, slots=True)
class ReportEmployeeGroup:
    employee_id: int
    employee_name: str
    work_labels: list[str]
    columns: list[str]


@dataclass(frozen=True, slots=True)
class ReportRow:
    date_label: str
    values: list[str]
    total_amount: int


@dataclass(frozen=True, slots=True)
class ReportRenderModel:
    team: Team
    period: ReportPeriodOption
    employee_count: int
    employee_groups: list[ReportEmployeeGroup] = field(default_factory=list)
    columns: list[ReportColumn] = field(default_factory=list)
    rows: list[ReportRow] = field(default_factory=list)
    total_amount: int = 0
    total_workdays: int = 0


WORK_CODE_BY_NAME = {
    "Thừa máy": "TM",
    "Máy nhỏ": "MN",
    "Máy to": "MT",
    "Phụ cắt": "PC",
    "Phụ găng 1 máy": "PG1",
    "Phụ găng 2 máy": "PG2",
}
NORMALIZED_WORK_CODE_BY_NAME = {
    re.sub(r"\s+", " ", unicodedata.normalize("NFC", name).strip()).casefold(): code
    for name, code in WORK_CODE_BY_NAME.items()
}
DEFAULT_BLOW_CODE_ORDER = ["TM", "MN", "MT", "PC", "PG1", "PG2"]


class AttendanceReportService:
    def __init__(self, session_factory: sessionmaker[Session] = AttendanceSessionLocal) -> None:
        self._session_factory = session_factory

    def list_periods(self) -> list[ReportPeriodOption]:
        from modules.attendance.models import Period

        with self._session_factory() as session:
            periods = session.scalars(select(Period).order_by(Period.start_date.desc())).all()
            return [self._to_period_option(period) for period in periods]

    def build_report(self, *, team: Team | str, period_id: int, today: date | None = None) -> ReportRenderModel:
        from modules.attendance.models import Period

        resolved_team = self._coerce_team(team)
        current_day = today or date.today()
        with self._session_factory() as session:
            period = session.get(Period, period_id)
            if period is None:
                raise NotFoundError("period not found")
            period_option = self._to_period_option(period)
            visible_dates = self._visible_dates(period.start_date, period.end_date, current_day)
            employees = self._list_report_employees(session, resolved_team, period.start_date, period.end_date)
            records = self._list_records(session, [employee.id for employee in employees], visible_dates)
            record_by_employee_day = {(record.employee_id, record.date): record for record in records}

            employee_groups: list[ReportEmployeeGroup] = []
            columns: list[ReportColumn] = [ReportColumn(kind="date", label="Ngày")]
            for employee in employees:
                work_labels = self._visible_subcolumns(resolved_team, employee.id, visible_dates, record_by_employee_day, session)
                group_columns = [*work_labels, "Tổng"]
                employee_groups.append(
                    ReportEmployeeGroup(
                        employee_id=employee.id,
                        employee_name=employee.name,
                        work_labels=work_labels,
                        columns=group_columns,
                    )
                )
                for label in group_columns:
                    columns.append(
                        ReportColumn(
                            kind="employee_total" if label == "Tổng" else "employee_value",
                            label=label,
                            employee_id=employee.id,
                            employee_name=employee.name,
                        )
                    )
            columns.append(ReportColumn(kind="day_total", label="Tổng tiền cả ngày"))

            rows: list[ReportRow] = []
            total_amount = 0
            total_workdays = 0
            for day in visible_dates:
                values = [day.strftime("%d/%m")]
                day_total = 0
                for group in employee_groups:
                    record = record_by_employee_day.get((group.employee_id, day))
                    work_values = self._work_values_for_record(resolved_team, record)
                    amount = 0 if record is None or record.is_absent else int(record.total_amount_snapshot)
                    for label in group.work_labels:
                        values.append(self._format_work_value(work_values.get(label)))
                    values.append(self._format_money(amount))
                    day_total += amount
                    if amount > 0:
                        total_workdays += 1
                values.append(self._format_money(day_total))
                total_amount += day_total
                rows.append(ReportRow(date_label=day.strftime("%d/%m"), values=values, total_amount=day_total))

            return ReportRenderModel(
                team=resolved_team,
                period=period_option,
                employee_count=len(employees),
                employee_groups=employee_groups,
                columns=columns,
                rows=rows,
                total_amount=total_amount,
                total_workdays=total_workdays,
            )

    def _list_report_employees(self, session: Session, team: Team, start_date: date, end_date: date) -> list[Employee]:
        history_employee_ids = set(
            session.scalars(
                select(DailyRecord.employee_id)
                .where(DailyRecord.date >= start_date)
                .where(DailyRecord.date <= end_date)
                .distinct()
            ).all()
        )
        statement = (
            select(Employee)
            .where(Employee.team == team)
            .where((Employee.is_active.is_(True)) | (Employee.id.in_(history_employee_ids)))
            .order_by(Employee.name.asc())
        )
        return list(session.scalars(statement).all())

    def _list_records(self, session: Session, employee_ids: list[int], visible_dates: list[date]) -> list[DailyRecord]:
        if not employee_ids or not visible_dates:
            return []
        return list(
            session.scalars(
                select(DailyRecord)
                .options(
                    selectinload(DailyRecord.work_logs).selectinload(WorkLog.work_type),
                    selectinload(DailyRecord.cut_logs).selectinload(CutLog.bag_type),
                )
                .where(DailyRecord.employee_id.in_(employee_ids))
                .where(DailyRecord.date >= visible_dates[0])
                .where(DailyRecord.date <= visible_dates[-1])
            ).all()
        )

    def _visible_subcolumns(
        self,
        team: Team,
        employee_id: int,
        visible_dates: list[date],
        record_by_employee_day: dict[tuple[int, date], DailyRecord],
        session: Session,
    ) -> list[str]:
        used_labels: set[str] = set()
        for day in visible_dates:
            record = record_by_employee_day.get((employee_id, day))
            for label, raw_value in self._work_values_for_record(team, record).items():
                if self._has_value(raw_value):
                    used_labels.add(label)
        if team == Team.BLOW:
            ordered_labels = [label for label in DEFAULT_BLOW_CODE_ORDER if label in used_labels]
            ordered_labels.extend(sorted(used_labels - set(ordered_labels)))
            return ordered_labels
        ordered = [self._abbreviate_bag_label(bag_type.name) for bag_type in session.scalars(select(BagType).order_by(BagType.id.asc())).all()]
        ordered.extend(sorted(used_labels - set(ordered)))
        return [label for label in ordered if label in used_labels]

    def _work_values_for_record(self, team: Team, record: DailyRecord | None) -> dict[str, object]:
        if record is None or record.is_absent:
            return {}
        if team == Team.BLOW:
            values: dict[str, object] = {}
            for log in record.work_logs:
                label = self._work_code(log.work_type.name)
                values[label] = True if log.work_type.input_type == WorkInputType.TICK else log.quantity
            return values
        values = {}
        for log in record.cut_logs:
            values[self._abbreviate_bag_label(log.bag_type.name)] = log.quantity
        return values

    def _visible_dates(self, start_date: date, end_date: date, today: date) -> list[date]:
        visible_end = min(end_date, today)
        if visible_end < start_date:
            return []
        days: list[date] = []
        cursor = start_date
        while cursor <= visible_end:
            days.append(cursor)
            cursor += timedelta(days=1)
        return days

    def _to_period_option(self, period) -> ReportPeriodOption:
        return ReportPeriodOption(
            id=period.id,
            label=f"Kỳ {period.start_date.strftime('%d/%m/%Y')} - {period.end_date.strftime('%d/%m/%Y')}",
            start_date=period.start_date,
            end_date=period.end_date,
        )

    def _coerce_team(self, team: Team | str) -> Team:
        if isinstance(team, Team):
            return team
        try:
            return Team(team)
        except ValueError as exc:
            raise ValidationError("invalid team") from exc

    def _work_code(self, work_name: str) -> str:
        normalized_name = re.sub(r"\s+", " ", unicodedata.normalize("NFC", work_name).strip()).casefold()
        return NORMALIZED_WORK_CODE_BY_NAME.get(normalized_name, work_name)

    def _abbreviate_bag_label(self, bag_type_name: str) -> str:
        for token in bag_type_name.replace("-", " ").split():
            lowered = token.casefold()
            if lowered.endswith("kg"):
                return token
            if token.upper() == "PP":
                return "PP"
        return bag_type_name.replace("Bao", "").strip() or bag_type_name

    def _has_value(self, raw_value: object) -> bool:
        if isinstance(raw_value, bool):
            return raw_value
        if raw_value is None:
            return False
        if isinstance(raw_value, (int, float)):
            return raw_value != 0
        return str(raw_value).strip() != ""

    def _format_work_value(self, raw_value: object) -> str:
        if isinstance(raw_value, bool):
            return "1" if raw_value else ""
        if raw_value in (None, "", 0):
            return ""
        return str(raw_value)

    def _format_money(self, amount: int) -> str:
        return f"{amount:,}"
