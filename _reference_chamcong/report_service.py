from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from datetime import timedelta


@dataclass(frozen=True)
class ReportColumn:
    kind: str
    label: str
    employee_name: str | None = None


@dataclass(frozen=True)
class ReportRow:
    values: list[str]


@dataclass(frozen=True)
class ReportEmployeeGroup:
    employee_name: str
    work_labels: list[str]
    columns: list[str]


@dataclass(frozen=True)
class ReportRenderModel:
    team_key: str
    employee_count: int
    employee_groups: list[ReportEmployeeGroup]
    columns: list[ReportColumn]
    rows: list[ReportRow]
    total_amount: int
    total_workdays: int


def build_mock_report_dataset() -> tuple[list[str], dict[tuple[str, str], dict[str, object]]]:
    report_periods = [
        "Kỳ 01/04/2026 - 10/04/2026",
        "Kỳ 11/04/2026 - 20/04/2026",
        "Kỳ 21/04/2026 - 30/04/2026",
    ]
    report_views_by_team_period = {
        ("blow", report_periods[0]): _build_mock_report_period(
            report_periods[0],
            ["Nguyen Van An", "Le Quoc Cuong", "Hoang Minh Em"],
            {
                "01/04": {
                    "Nguyen Van An": {"values": {"TM": 2, "MN": 5}, "total": 210000},
                    "Le Quoc Cuong": {"values": {"PG1": True}, "total": 30000},
                    "Hoang Minh Em": {"values": {}, "total": 0},
                },
                "02/04": {
                    "Nguyen Van An": {"values": {"PC": 3}, "total": 150000},
                    "Le Quoc Cuong": {"values": {"MT": 1, "PG2": True}, "total": 90000},
                    "Hoang Minh Em": {"values": {"MN": 2}, "total": 60000},
                },
                "03/04": {
                    "Nguyen Van An": {"values": {}, "total": 0, "absent": True},
                    "Le Quoc Cuong": {"values": {"TM": 1}, "total": 80000},
                    "Hoang Minh Em": {"values": {"PC": 2}, "total": 100000},
                },
                "04/04": {
                    "Nguyen Van An": {"values": {"PG1": True}, "total": 30000},
                    "Le Quoc Cuong": {"values": {"MN": 4}, "total": 120000},
                    "Hoang Minh Em": {"values": {"MT": 2}, "total": 80000},
                },
                "05/04": {
                    "Nguyen Van An": {"values": {"MT": 1}, "total": 40000},
                    "Le Quoc Cuong": {"values": {}, "total": 0},
                    "Hoang Minh Em": {"values": {"PG2": True}, "total": 50000},
                },
            },
        ),
        ("cut", report_periods[0]): _build_mock_report_period(
            report_periods[0],
            ["Tran Thi Binh", "Pham Thi Dung"],
            {
                "01/04": {
                    "Tran Thi Binh": {"values": {"25kg": 12}, "total": 42000},
                    "Pham Thi Dung": {"values": {"50kg": 6}, "total": 25200},
                },
                "02/04": {
                    "Tran Thi Binh": {"values": {"50kg": 8}, "total": 33600},
                    "Pham Thi Dung": {"values": {}, "total": 0, "absent": True},
                },
                "03/04": {
                    "Tran Thi Binh": {"values": {"25kg": 10, "50kg": 2}, "total": 43400},
                    "Pham Thi Dung": {"values": {"25kg": 8}, "total": 28000},
                },
                "04/04": {
                    "Tran Thi Binh": {"values": {}, "total": 0},
                    "Pham Thi Dung": {"values": {"50kg": 5}, "total": 21000},
                },
                "05/04": {
                    "Tran Thi Binh": {"values": {"50kg": 6}, "total": 25200},
                    "Pham Thi Dung": {"values": {"25kg": 10}, "total": 35000},
                },
            },
        ),
        ("blow", report_periods[1]): _build_mock_report_period(
            report_periods[1],
            ["Nguyen Van An", "Le Quoc Cuong", "Hoang Minh Em"],
            {
                "11/04": {
                    "Nguyen Van An": {"values": {"TM": 1}, "total": 80000},
                    "Le Quoc Cuong": {"values": {"MN": 3}, "total": 90000},
                    "Hoang Minh Em": {"values": {"PG1": True}, "total": 30000},
                },
                "12/04": {
                    "Nguyen Van An": {"values": {"PC": 2}, "total": 100000},
                    "Le Quoc Cuong": {"values": {}, "total": 0},
                    "Hoang Minh Em": {"values": {"MT": 1}, "total": 40000},
                },
                "13/04": {
                    "Nguyen Van An": {"values": {}, "total": 0},
                    "Le Quoc Cuong": {"values": {"TM": 2, "PG2": True}, "total": 210000},
                    "Hoang Minh Em": {"values": {"MN": 1}, "total": 30000},
                },
                "14/04": {
                    "Nguyen Van An": {"values": {"PG1": True}, "total": 30000},
                    "Le Quoc Cuong": {"values": {"PC": 1}, "total": 50000},
                    "Hoang Minh Em": {"values": {}, "total": 0, "absent": True},
                },
                "15/04": {
                    "Nguyen Van An": {"values": {"MN": 2}, "total": 60000},
                    "Le Quoc Cuong": {"values": {"MT": 2}, "total": 80000},
                    "Hoang Minh Em": {"values": {"PG2": True}, "total": 50000},
                },
            },
        ),
        ("cut", report_periods[1]): _build_mock_report_period(
            report_periods[1],
            ["Tran Thi Binh", "Pham Thi Dung"],
            {
                "11/04": {
                    "Tran Thi Binh": {"values": {"25kg": 15}, "total": 52500},
                    "Pham Thi Dung": {"values": {"50kg": 4}, "total": 16800},
                },
                "12/04": {
                    "Tran Thi Binh": {"values": {}, "total": 0, "absent": True},
                    "Pham Thi Dung": {"values": {"25kg": 9, "50kg": 3, "PP": 4}, "total": 59700},
                },
                "13/04": {
                    "Tran Thi Binh": {"values": {"50kg": 7}, "total": 29400},
                    "Pham Thi Dung": {"values": {}, "total": 0},
                },
                "14/04": {
                    "Tran Thi Binh": {"values": {"25kg": 11}, "total": 38500},
                    "Pham Thi Dung": {"values": {"25kg": 6}, "total": 21000},
                },
                "15/04": {
                    "Tran Thi Binh": {"values": {"50kg": 5}, "total": 21000},
                    "Pham Thi Dung": {"values": {"50kg": 8}, "total": 33600},
                },
            },
        ),
        ("blow", report_periods[2]): _build_mock_report_period(
            report_periods[2],
            ["Nguyen Van An", "Le Quoc Cuong", "Hoang Minh Em"],
            {
                "21/04": {
                    "Nguyen Van An": {"values": {"PG2": True}, "total": 50000},
                    "Le Quoc Cuong": {"values": {"TM": 1}, "total": 80000},
                    "Hoang Minh Em": {"values": {}, "total": 0},
                },
                "22/04": {
                    "Nguyen Van An": {"values": {"MN": 4}, "total": 120000},
                    "Le Quoc Cuong": {"values": {"PC": 2}, "total": 100000},
                    "Hoang Minh Em": {"values": {"PG1": True}, "total": 30000},
                },
                "23/04": {
                    "Nguyen Van An": {"values": {}, "total": 0, "absent": True},
                    "Le Quoc Cuong": {"values": {"MT": 2}, "total": 80000},
                    "Hoang Minh Em": {"values": {"TM": 1, "MN": 1}, "total": 110000},
                },
                "24/04": {
                    "Nguyen Van An": {"values": {"PC": 1}, "total": 50000},
                    "Le Quoc Cuong": {"values": {}, "total": 0},
                    "Hoang Minh Em": {"values": {"PG2": True}, "total": 50000},
                },
                "25/04": {
                    "Nguyen Van An": {"values": {"MT": 1}, "total": 40000},
                    "Le Quoc Cuong": {"values": {"MN": 2}, "total": 60000},
                    "Hoang Minh Em": {"values": {"PC": 3}, "total": 150000},
                },
            },
        ),
        ("cut", report_periods[2]): _build_mock_report_period(
            report_periods[2],
            ["Tran Thi Binh", "Pham Thi Dung"],
            {
                "21/04": {
                    "Tran Thi Binh": {"values": {"25kg": 10}, "total": 35000},
                    "Pham Thi Dung": {"values": {"50kg": 5}, "total": 21000},
                },
                "22/04": {
                    "Tran Thi Binh": {"values": {"50kg": 9}, "total": 37800},
                    "Pham Thi Dung": {"values": {}, "total": 0},
                },
                "23/04": {
                    "Tran Thi Binh": {"values": {}, "total": 0, "absent": True},
                    "Pham Thi Dung": {"values": {"25kg": 14}, "total": 49000},
                },
                "24/04": {
                    "Tran Thi Binh": {"values": {"25kg": 8, "50kg": 4}, "total": 44800},
                    "Pham Thi Dung": {"values": {"25kg": 6}, "total": 21000},
                },
                "25/04": {
                    "Tran Thi Binh": {"values": {"50kg": 6}, "total": 25200},
                    "Pham Thi Dung": {"values": {"50kg": 7}, "total": 29400},
                },
            },
        ),
    }
    return report_periods, report_views_by_team_period


def build_report_render_model(
    team_label: str,
    period_label: str,
    report_views_by_team_period: dict[tuple[str, str], dict[str, object]],
    cut_bag_types: list[dict[str, object]],
    *,
    today: date,
) -> ReportRenderModel:
    team_key = _report_team_key(team_label)
    report_view = report_views_by_team_period.get((team_key, period_label), {"employees": [], "rows": []})
    employees = list(report_view.get("employees", []))
    source_rows = _filter_visible_report_rows(period_label, list(report_view.get("rows", [])), today=today)

    employee_groups: list[ReportEmployeeGroup] = []
    columns: list[ReportColumn] = [ReportColumn(kind="date", label="Ngày")]
    for employee_name in employees:
        visible_work_labels = _visible_report_subcolumns(team_key, employee_name, source_rows, cut_bag_types)
        group_columns = [*visible_work_labels, "Tổng"]
        employee_groups.append(
            ReportEmployeeGroup(
                employee_name=employee_name,
                work_labels=visible_work_labels,
                columns=group_columns,
            )
        )
        for subcolumn in group_columns:
            columns.append(
                ReportColumn(
                    kind="employee_total" if subcolumn == "Tổng" else "employee_value",
                    employee_name=employee_name,
                    label=subcolumn,
                )
            )
    columns.append(ReportColumn(kind="day_total", label="Tổng tiền cả ngày"))

    rendered_rows: list[ReportRow] = []
    total_amount = 0
    total_workdays = 0
    for row_data in source_rows:
        rendered_values: list[str] = [str(row_data.get("date", ""))]
        row_total = 0
        cell_map = row_data.get("cells", {})
        if not isinstance(cell_map, dict):
            cell_map = {}

        for group in employee_groups:
            cell_data = _normalize_mock_report_cell(cell_map.get(group.employee_name))
            work_values = cell_data["values"]
            assert isinstance(work_values, dict)
            amount = int(cell_data["total"])
            for subcolumn in group.work_labels:
                rendered_values.append(_format_report_work_value(work_values.get(str(subcolumn))))
            rendered_values.append(_format_money(amount))
            row_total += amount
            if amount > 0:
                total_workdays += 1

        rendered_values.append(_format_money(row_total))
        total_amount += row_total
        rendered_rows.append(ReportRow(values=rendered_values))

    return ReportRenderModel(
        team_key=team_key,
        employee_count=len(employees),
        employee_groups=employee_groups,
        columns=columns,
        rows=rendered_rows,
        total_amount=total_amount,
        total_workdays=total_workdays,
    )


def _build_mock_report_period(
    period_label: str,
    employees: list[str],
    entries_by_date: dict[str, dict[str, dict[str, object]]],
) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for date_label in _report_period_date_labels(period_label):
        source_row = entries_by_date.get(date_label, {})
        rows.append(
            {
                "date": date_label,
                "cells": {
                    employee_name: _normalize_mock_report_cell(source_row.get(employee_name))
                    for employee_name in employees
                },
            }
        )
    return {"employees": employees, "rows": rows}


def _normalize_mock_report_cell(cell_data: object) -> dict[str, object]:
    if not isinstance(cell_data, dict):
        return {"values": {}, "total": 0, "absent": False}
    values = cell_data.get("values", {})
    normalized_values = dict(values) if isinstance(values, dict) else {}
    return {
        "values": normalized_values,
        "total": int(cell_data.get("total", 0) or 0),
        "absent": bool(cell_data.get("absent", False)),
    }


def _report_period_date_labels(period_label: str) -> list[str]:
    parts = [int(value) for value in re.findall(r"\d+", period_label)]
    if len(parts) < 6:
        return []
    start_date, end_date = _parse_report_period_bounds(period_label)
    return [current_day.strftime("%d/%m") for current_day in _daterange(start_date, end_date)]


def _report_team_key(team_label: str) -> str:
    lowered = team_label.casefold()
    return "cut" if "cắt" in lowered or "cáº¯t" in lowered else "blow"


def _filter_visible_report_rows(
    period_label: str,
    rows: list[dict[str, object]],
    *,
    today: date,
) -> list[dict[str, object]]:
    start_date, end_date = _parse_report_period_bounds(period_label)
    visible_end_date = min(end_date, today)
    if visible_end_date < start_date:
        return []
    visible_labels = {
        current_day.strftime("%d/%m")
        for current_day in _daterange(start_date, visible_end_date)
    }
    return [row_data for row_data in rows if str(row_data.get("date", "")) in visible_labels]


def _parse_report_period_bounds(period_label: str) -> tuple[date, date]:
    parts = [int(value) for value in re.findall(r"\d+", period_label)]
    return date(parts[2], parts[1], parts[0]), date(parts[5], parts[4], parts[3])


def _daterange(start_date: date, end_date: date) -> list[date]:
    days: list[date] = []
    current_day = start_date
    while current_day <= end_date:
        days.append(current_day)
        current_day += timedelta(days=1)
    return days


def _visible_report_subcolumns(
    team_key: str,
    employee_name: str,
    rows: list[dict[str, object]],
    cut_bag_types: list[dict[str, object]],
) -> list[str]:
    used_labels: set[str] = set()
    for row_data in rows:
        cell_map = row_data.get("cells", {})
        if not isinstance(cell_map, dict):
            continue
        cell_data = _normalize_mock_report_cell(cell_map.get(employee_name))
        work_values = cell_data["values"]
        assert isinstance(work_values, dict)
        for label, raw_value in work_values.items():
            if _has_report_work_value(raw_value):
                used_labels.add(str(label))

    if team_key == "blow":
        ordered_labels = ["TM", "MN", "MT", "PC", "PG1", "PG2"]
    else:
        ordered_labels = _cut_report_column_order(rows, cut_bag_types)
    return [label for label in ordered_labels if label in used_labels]


def _cut_report_column_order(
    rows: list[dict[str, object]],
    cut_bag_types: list[dict[str, object]],
) -> list[str]:
    ordered_labels: list[str] = []
    seen_labels: set[str] = set()

    for bag_type in cut_bag_types:
        label = _abbreviate_cut_report_label(str(bag_type.get("name", "")))
        if label and label not in seen_labels:
            ordered_labels.append(label)
            seen_labels.add(label)

    for row_data in rows:
        cell_map = row_data.get("cells", {})
        if not isinstance(cell_map, dict):
            continue
        for cell_data in cell_map.values():
            normalized = _normalize_mock_report_cell(cell_data)
            work_values = normalized["values"]
            assert isinstance(work_values, dict)
            for label in work_values:
                text = str(label)
                if text not in seen_labels:
                    ordered_labels.append(text)
                    seen_labels.add(text)
    return ordered_labels


def _abbreviate_cut_report_label(bag_type_name: str) -> str:
    for token in bag_type_name.replace("-", " ").split():
        lowered = token.casefold()
        if lowered.endswith("kg"):
            return token
        if token.upper() == "PP":
            return "PP"
    return bag_type_name.replace("Bao", "").strip()


def _has_report_work_value(raw_value: object) -> bool:
    if isinstance(raw_value, bool):
        return raw_value
    if raw_value is None:
        return False
    if isinstance(raw_value, (int, float)):
        return raw_value != 0
    return str(raw_value).strip() != ""


def _format_report_work_value(raw_value: object) -> str:
    if isinstance(raw_value, bool):
        return "1" if raw_value else ""
    if raw_value in (None, "", 0):
        return ""
    return str(raw_value)


def _format_money(amount: int) -> str:
    return f"{amount:,}"
