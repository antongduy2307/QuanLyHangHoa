from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal
import re
import unicodedata

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, sessionmaker

from core.exceptions import NotFoundError, ValidationError
from modules.attendance.db import AttendanceSessionLocal
from modules.attendance.models import BagType, CutLog, DailyRecord, Employee, ExtraCutWorkLog, Team, WorkInputType, WorkLog, WorkType


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
    is_total: bool = False


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


@dataclass(frozen=True, slots=True)
class MonthlyReportRow:
    employee_name: str
    values: list[str]
    total_amount: int
    is_total: bool = False


@dataclass(frozen=True, slots=True)
class MonthlyReportRenderModel:
    team: Team
    month_start: date
    month_end: date
    employee_count: int
    columns: list[str] = field(default_factory=list)
    rows: list[MonthlyReportRow] = field(default_factory=list)
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
DEFAULT_BLOW_CODE_ORDER = ["TM", "MN", "MT", "PC", "PG1", "PG2", "VK"]


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
            employee_period_totals = {employee.id: 0 for employee in employees}
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
                    employee_period_totals[group.employee_id] += amount
                    day_total += amount
                    if amount > 0:
                        total_workdays += 1
                values.append(self._format_money(day_total))
                total_amount += day_total
                rows.append(ReportRow(date_label=day.strftime("%d/%m"), values=values, total_amount=day_total))
            rows.append(
                ReportRow(
                    date_label="Tổng",
                    values=self._period_total_row_values(employee_groups, employee_period_totals, total_amount),
                    total_amount=total_amount,
                    is_total=True,
                )
            )

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

    def build_monthly_report(self, *, team: Team | str, month_date: date) -> MonthlyReportRenderModel:
        resolved_team = self._coerce_team(team)
        month_start, month_end = self.month_date_range(month_date)
        dates = self._date_range(month_start, month_end)
        with self._session_factory() as session:
            employees = self._list_report_employees(session, resolved_team, month_start, month_end)
            records = self._list_records(session, [employee.id for employee in employees], dates)
            records_by_employee: dict[int, list[DailyRecord]] = {employee.id: [] for employee in employees}
            for record in records:
                records_by_employee.setdefault(record.employee_id, []).append(record)

            used_labels: set[str] = set()
            employee_values: dict[int, dict[str, Decimal | int]] = {}
            employee_totals: dict[int, int] = {}
            total_workdays = 0
            for employee in employees:
                values: dict[str, Decimal | int] = {}
                total_amount = 0
                for record in records_by_employee.get(employee.id, []):
                    if record.is_absent:
                        continue
                    for label, amount in self._monthly_values_for_record(resolved_team, record).items():
                        values[label] = values.get(label, 0) + amount
                        if amount:
                            used_labels.add(label)
                    record_amount = int(record.total_amount_snapshot)
                    total_amount += record_amount
                    if record_amount > 0:
                        total_workdays += 1
                employee_values[employee.id] = values
                employee_totals[employee.id] = total_amount

            detail_labels = self._monthly_detail_labels(resolved_team, used_labels, session)
            rows: list[MonthlyReportRow] = []
            detail_totals = {label: 0 for label in detail_labels}
            total_amount_all = 0
            for employee in employees:
                values = [employee.name]
                totals = employee_values.get(employee.id, {})
                for label in detail_labels:
                    raw_value = totals.get(label, 0)
                    detail_totals[label] += raw_value
                    values.append(self._format_monthly_detail_value(label, raw_value))
                employee_total = employee_totals.get(employee.id, 0)
                total_amount_all += employee_total
                values.append(self._format_money(employee_total))
                rows.append(MonthlyReportRow(employee_name=employee.name, values=values, total_amount=employee_total))

            total_values = ["Tổng"]
            for label in detail_labels:
                total_values.append(self._format_monthly_detail_value(label, detail_totals.get(label, 0)))
            total_values.append(self._format_money(total_amount_all))
            rows.append(MonthlyReportRow(employee_name="Tổng", values=total_values, total_amount=total_amount_all, is_total=True))

            return MonthlyReportRenderModel(
                team=resolved_team,
                month_start=month_start,
                month_end=month_end,
                employee_count=len(employees),
                columns=["Tên nhân viên", *detail_labels, "Tổng tiền"],
                rows=rows,
                total_amount=total_amount_all,
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
                    selectinload(DailyRecord.extra_cut_work_logs).selectinload(ExtraCutWorkLog.bag_type),
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
            extra_cut_amount = sum(log.amount_snapshot for log in record.extra_cut_work_logs)
            if extra_cut_amount > 0:
                values["VK"] = self._format_money(extra_cut_amount)
            return values
        values = {}
        for log in record.cut_logs:
            values[self._abbreviate_bag_label(log.bag_type.name)] = log.quantity
        return values

    def _visible_dates(self, start_date: date, end_date: date, today: date) -> list[date]:
        visible_end = min(end_date, today)
        if visible_end < start_date:
            return []
        return self._date_range(start_date, visible_end)

    def _date_range(self, start_date: date, end_date: date) -> list[date]:
        days: list[date] = []
        cursor = start_date
        while cursor <= end_date:
            days.append(cursor)
            cursor += timedelta(days=1)
        return days

    def month_date_range(self, month_date: date) -> tuple[date, date]:
        last_day = monthrange(month_date.year, month_date.month)[1]
        return date(month_date.year, month_date.month, 1), date(month_date.year, month_date.month, last_day)

    def _monthly_values_for_record(self, team: Team, record: DailyRecord) -> dict[str, Decimal | int]:
        if team == Team.BLOW:
            values: dict[str, Decimal | int] = {}
            for log in record.work_logs:
                label = self._work_code(log.work_type.name)
                amount = 1 if log.work_type.input_type == WorkInputType.TICK else int(log.quantity)
                values[label] = values.get(label, 0) + amount
            extra_cut_amount = sum(int(log.amount_snapshot) for log in record.extra_cut_work_logs)
            if extra_cut_amount > 0:
                values["VK"] = values.get("VK", 0) + extra_cut_amount
            return values

        values: dict[str, Decimal | int] = {}
        for log in record.cut_logs:
            label = self._abbreviate_bag_label(log.bag_type.name)
            values[label] = self._to_decimal_quantity(values.get(label, Decimal("0"))) + self._to_decimal_quantity(log.quantity)
        return values

    def _monthly_detail_labels(self, team: Team, used_labels: set[str], session: Session) -> list[str]:
        if team == Team.BLOW:
            ordered_labels = [label for label in DEFAULT_BLOW_CODE_ORDER if label in used_labels]
            ordered_labels.extend(sorted(used_labels - set(ordered_labels)))
            return ordered_labels
        ordered = [self._abbreviate_bag_label(bag_type.name) for bag_type in session.scalars(select(BagType).order_by(BagType.id.asc())).all()]
        ordered.extend(sorted(used_labels - set(ordered)))
        return [label for label in ordered if label in used_labels]

    def _format_monthly_detail_value(self, label: str, raw_value: Decimal | int) -> str:
        if raw_value == 0:
            return ""
        if label == "VK":
            return self._format_money(int(raw_value))
        return self._format_quantity(raw_value)

    def _period_total_row_values(
        self,
        employee_groups: list[ReportEmployeeGroup],
        employee_period_totals: dict[int, int],
        total_amount: int,
    ) -> list[str]:
        values = ["Tổng"]
        for group in employee_groups:
            for _label in group.work_labels:
                values.append("")
            values.append(self._format_money(employee_period_totals.get(group.employee_id, 0)))
        values.append(self._format_money(total_amount))
        return values

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
        if isinstance(raw_value, (int, Decimal)):
            return raw_value != 0
        return str(raw_value).strip() != ""

    def _format_work_value(self, raw_value: object) -> str:
        if isinstance(raw_value, bool):
            return "1" if raw_value else ""
        if raw_value in (None, "", 0):
            return ""
        if isinstance(raw_value, Decimal):
            return self._format_quantity(raw_value)
        return str(raw_value)

    def _format_money(self, amount: int) -> str:
        return f"{amount:,}"

    def _format_quantity(self, quantity: Decimal | int) -> str:
        value = self._to_decimal_quantity(quantity)
        text = format(value.normalize(), "f")
        return text.rstrip("0").rstrip(".") if "." in text else text

    def _to_decimal_quantity(self, quantity: Decimal | int) -> Decimal:
        if isinstance(quantity, Decimal):
            return quantity
        return Decimal(str(quantity))
