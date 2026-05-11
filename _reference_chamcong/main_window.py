from __future__ import annotations

import calendar
import re
import sys
from datetime import date
from datetime import timedelta
from pathlib import Path

from PyQt6.QtCore import QDate
from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtCore import QModelIndex
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker
from sqlalchemy.orm import selectinload

from models import BagType
from models import Base
from models import CutLog
from models import DailyRecord
from models import DailyRecordStatus
from models import Employee
from models import EmployeeShiftPeriod
from models import Period
from models import Team
from models import WorkInputType
from models import WorkLog
from models import WorkType
from services import LockedPeriodError
from services import NotFoundError
from services import ValidationError
from services import add_blow_work
from services import add_cut_work
from services import create_period
from services import get_or_create_daily_record
from services import set_daily_record_absent


class EmployeeDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        title: str,
        name: str = "",
        team_label: str = "Tổ thổi",
        is_active: bool = True,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.resize(360, 180)

        layout = QVBoxLayout(self)

        form_layout = QFormLayout()
        self.name_input = QLineEdit(name)
        self.team_combo = QComboBox()
        self.team_combo.addItems(["Tổ thổi", "Tổ cắt"])
        self.team_combo.setCurrentText(team_label)
        self.active_checkbox = QCheckBox("Đang hoạt động")
        self.active_checkbox.setChecked(is_active)
        form_layout.addRow("Tên hiển thị", self.name_input)
        form_layout.addRow("Tổ", self.team_combo)
        form_layout.addRow("", self.active_checkbox)
        layout.addLayout(form_layout)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_form_data(self) -> dict[str, object]:
        return {
            "name": self.name_input.text().strip(),
            "team_label": self.team_combo.currentText(),
            "is_active": self.active_checkbox.isChecked(),
        }


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("chamcong")
        self.resize(1360, 800)

        self.db_path = Path(__file__).resolve().with_name("chamcong.db")
        self.engine = create_engine(f"sqlite:///{self.db_path}", future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, future=True, expire_on_commit=False)

        self.employees: list[dict] = []
        self.attendance_status_map: dict[int, str] = {}
        self.report_periods: list[str] = []
        self.blow_work_configs: list[dict] = []
        self.cut_bag_types: list[dict] = []
        self.report_views_by_team_period: dict[tuple[str, str], dict[str, object]] = {}
        self.selected_employee_id: int | None = None
        self.current_daily_record_id: int | None = None
        self.current_daily_record_status: str = "-"
        self.blow_quantity_controls: dict[str, dict[str, object]] = {}
        self.blow_glove_checkboxes: dict[str, QCheckBox] = {}
        self.report_header_top_labels: list[QLabel] = []
        self.report_header_bottom_labels: list[QLabel] = []

        self.setup_database()
        self.populate_mock_data()
        self._build_ui()
        self.reload_all_ui_data()

        if self.attendance_employee_table.rowCount() > 0:
            self.attendance_employee_table.selectRow(0)
            self.update_attendance_form_for_selected_employee()

    def setup_database(self) -> None:
        Base.metadata.create_all(self.engine)
        self.ensure_schema_updates()
        with self.SessionLocal() as session:
            self.seed_initial_data(session)
            session.commit()

    def ensure_schema_updates(self) -> None:
        with self.engine.begin() as connection:
            columns = {
                row[1]
                for row in connection.exec_driver_sql("PRAGMA table_info(daily_records)").fetchall()
            }
            if "is_absent" not in columns:
                connection.exec_driver_sql(
                    "ALTER TABLE daily_records ADD COLUMN is_absent BOOLEAN NOT NULL DEFAULT 0"
                )

    def seed_initial_data(self, session: Session) -> None:
        self.ensure_period_for_date(session, date.today())

        if session.scalar(select(Employee.id).limit(1)) is None:
            session.add_all(
                [
                    Employee(name="Nguyen Van An", team=Team.BLOW, is_active=True),
                    Employee(name="Tran Thi Binh", team=Team.CUT, is_active=True),
                    Employee(name="Le Quoc Cuong", team=Team.BLOW, is_active=True),
                    Employee(name="Pham Thi Dung", team=Team.CUT, is_active=False),
                    Employee(name="Hoang Minh Em", team=Team.BLOW, is_active=True),
                ]
            )

        blow_work_types = [
            ("Thừa máy", WorkInputType.QUANTITY, 80000),
            ("Máy nhỏ", WorkInputType.QUANTITY, 30000),
            ("Máy to", WorkInputType.QUANTITY, 40000),
            ("Phụ cắt", WorkInputType.QUANTITY, 50000),
            ("Phụ găng 1 máy", WorkInputType.TICK, 30000),
            ("Phụ găng 2 máy", WorkInputType.TICK, 50000),
        ]
        existing_work_names = set(session.scalars(select(WorkType.name)).all())
        for name, input_type, unit_price in blow_work_types:
            if name not in existing_work_names:
                session.add(
                    WorkType(
                        name=name,
                        team=Team.BLOW,
                        input_type=input_type,
                        unit_price=unit_price,
                        is_active=True,
                    )
                )

        cut_bag_types = [
            ("Bao 25kg", 3500, True),
            ("Bao 50kg", 4200, True),
            ("Bao PP", 3900, False),
        ]
        existing_bag_names = set(session.scalars(select(BagType.name)).all())
        for name, unit_price, is_active in cut_bag_types:
            if name not in existing_bag_names:
                session.add(BagType(name=name, unit_price=unit_price, is_active=is_active))

    def ensure_period_for_date(self, session: Session, selected_day: date) -> None:
        period = session.scalar(
            select(Period).where(
                Period.start_date <= selected_day,
                Period.end_date >= selected_day,
            )
        )
        if period is not None:
            return

        start_day, end_day = self._calculate_cycle_bounds(selected_day)
        create_period(session, start_day, end_day)

    def populate_mock_data(self) -> None:
        self.report_periods = []
        self.report_views_by_team_period = {}

    def _build_mock_report_period(
        self,
        period_label: str,
        employees: list[str],
        entries_by_date: dict[str, dict[str, dict[str, object]]],
    ) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        for date_label in self._report_period_date_labels(period_label):
            source_row = entries_by_date.get(date_label, {})
            rows.append(
                {
                    "date": date_label,
                    "cells": {
                        employee_name: self._normalize_mock_report_cell(source_row.get(employee_name))
                        for employee_name in employees
                    },
                }
            )
        return {"employees": employees, "rows": rows}

    def _normalize_mock_report_cell(self, cell_data: object) -> dict[str, object]:
        if not isinstance(cell_data, dict):
            return {"values": {}, "total": 0, "absent": False}
        values = cell_data.get("values", {})
        normalized_values = dict(values) if isinstance(values, dict) else {}
        return {
            "values": normalized_values,
            "total": int(cell_data.get("total", 0) or 0),
            "absent": bool(cell_data.get("absent", False)),
        }

    def _report_period_date_labels(self, period_label: str) -> list[str]:
        parts = [int(value) for value in re.findall(r"\d+", period_label)]
        if len(parts) < 6:
            return []
        start_date, end_date = self._parse_report_period_bounds(period_label)
        return [current_day.strftime("%d/%m") for current_day in self._daterange(start_date, end_date)]

    def _build_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root_layout = QVBoxLayout(central_widget)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(10)

        self.tab_widget = QTabWidget()
        root_layout.addWidget(self.tab_widget)

        self.tab_widget.addTab(self.build_tab_employees(), "Danh sách nhân viên")
        self.tab_widget.addTab(self.build_tab_attendance(), "Chấm công")
        self.tab_widget.addTab(self.build_tab_reports(), "Báo cáo")
        self.tab_widget.addTab(self.build_tab_settings(), "Cài đặt")

    def build_tab_employees(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        search_layout = QHBoxLayout()
        search_layout.addWidget(QLabel("Tìm nhân viên"))
        self.employee_search_input = QLineEdit()
        self.employee_search_input.setPlaceholderText("Nhập tên nhân viên...")
        self.employee_search_input.textChanged.connect(self.refresh_employee_table)
        search_layout.addWidget(self.employee_search_input, 1)
        layout.addLayout(search_layout)

        self.employee_table = QTableWidget(0, 3)
        self.employee_table.setHorizontalHeaderLabels(["Tên", "Tổ", "Trạng thái"])
        self.employee_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.employee_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.employee_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.employee_table.verticalHeader().setVisible(False)
        self.employee_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.employee_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.employee_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.employee_table, 1)

        button_layout = QHBoxLayout()
        for text in ["Thêm nhân viên", "Sửa nhân viên", "Xóa nhân viên"]:
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, label=text: self.show_placeholder_message(label))
            button_layout.addWidget(button)
        button_reload = QPushButton("Làm mới")
        button_reload.clicked.connect(self.reload_all_ui_data)
        button_layout.addWidget(button_reload)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        self._bind_employee_management_buttons(tab)
        return tab

    def build_tab_attendance(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        date_group = QGroupBox("Ngày chấm công")
        date_layout = QFormLayout(date_group)
        self.attendance_date_edit = QDateEdit()
        self.attendance_date_edit.setCalendarPopup(True)
        self.attendance_date_edit.setDisplayFormat("dd/MM/yyyy")
        self.attendance_date_edit.setDate(QDate.currentDate())
        date_layout.addRow("Chọn ngày", self.attendance_date_edit)
        left_layout.addWidget(date_group)

        self.attendance_list_title_label = QLabel("Nhân viên theo ngày")
        left_layout.addWidget(self.attendance_list_title_label)

        self.attendance_employee_table = QTableWidget(0, 3)
        self.attendance_employee_table.setHorizontalHeaderLabels(["Tên", "Tổ", "Trạng thái"])
        self.attendance_employee_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.attendance_employee_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.attendance_employee_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.attendance_employee_table.verticalHeader().setVisible(False)
        self.attendance_employee_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.attendance_employee_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.attendance_employee_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.attendance_employee_table.itemSelectionChanged.connect(self.update_attendance_form_for_selected_employee)
        self.attendance_date_edit.dateChanged.connect(self.on_attendance_date_changed)
        left_layout.addWidget(self.attendance_employee_table, 1)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)

        common_group = QGroupBox("Thông tin chấm công")
        common_form = QFormLayout(common_group)
        self.label_selected_employee = QLabel("-")
        self.label_selected_team = QLabel("-")
        self.label_selected_date = QLabel(self._format_attendance_date(self.get_selected_attendance_date()))
        self.label_selected_shift = QLabel("-")
        self.label_record_status = QLabel("-")
        common_form.addRow("Nhân viên", self.label_selected_employee)
        common_form.addRow("Tổ", self.label_selected_team)
        common_form.addRow("Ngày", self.label_selected_date)
        common_form.addRow("Ca trong kỳ", self.label_selected_shift)
        common_form.addRow("Trạng thái", self.label_record_status)

        self.absent_checkbox = QCheckBox("Đánh dấu nghỉ ngày này")
        self.absent_checkbox.toggled.connect(self.apply_absent_checkbox_state)

        self.status_hint_frame = QFrame()
        self.status_hint_frame.setFrameShape(QFrame.Shape.StyledPanel)
        status_layout = QVBoxLayout(self.status_hint_frame)
        self.status_hint_title = QLabel("Tiến độ bản ghi")
        self.status_hint_text = QLabel("Chọn nhân viên để bắt đầu tạo hoặc cập nhật bản ghi chấm công.")
        self.status_hint_text.setWordWrap(True)
        self.status_warning_label = QLabel("Cần hoàn thiện dữ liệu trước khi lưu.")
        self.status_warning_label.setWordWrap(True)
        self.status_warning_label.setVisible(False)
        status_layout.addWidget(self.status_hint_title)
        status_layout.addWidget(self.status_hint_text)
        status_layout.addWidget(self.status_warning_label)

        self.blow_group = QGroupBox("Nhập việc tổ thổi")
        blow_layout = QVBoxLayout(self.blow_group)
        blow_note = QLabel("Tích chọn việc phát sinh. Với việc nhập số lượng, ô số lượng chỉ xuất hiện khi đã chọn.")
        blow_note.setWordWrap(True)
        blow_layout.addWidget(blow_note)

        self.blow_rows_container = QWidget()
        self.blow_rows_layout = QVBoxLayout(self.blow_rows_container)
        self.blow_rows_layout.setContentsMargins(0, 0, 0, 0)
        self.blow_rows_layout.setSpacing(6)
        blow_layout.addWidget(self.blow_rows_container)

        self.cut_group = QGroupBox("Nhập việc tổ cắt")
        cut_layout = QVBoxLayout(self.cut_group)
        self.cut_table = QTableWidget(0, 2)
        self.cut_table.setHorizontalHeaderLabels(["Loại bao", "Số lượng"])
        self.cut_table.verticalHeader().setVisible(False)
        self.cut_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.cut_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        cut_layout.addWidget(self.cut_table)
        self.cut_note_label = QLabel("Ghi nhận loại bao trong ca. Có thể lưu và cập nhật lại cho ngày đã chọn.")
        self.cut_note_label.setWordWrap(True)
        cut_layout.addWidget(self.cut_note_label)

        cut_button_layout = QHBoxLayout()
        self.button_add_cut_row = QPushButton("Thêm dòng")
        self.button_remove_cut_row = QPushButton("Xóa dòng")
        self.button_add_cut_row.clicked.connect(self.add_cut_row)
        self.button_remove_cut_row.clicked.connect(self.remove_cut_row)
        cut_button_layout.addWidget(self.button_add_cut_row)
        cut_button_layout.addWidget(self.button_remove_cut_row)
        cut_button_layout.addStretch()
        cut_layout.addLayout(cut_button_layout)

        action_layout = QHBoxLayout()
        self.button_save_draft = QPushButton("Lưu nháp")
        self.button_finalize_day = QPushButton("Chốt ngày")
        self.button_copy_yesterday = QPushButton("Copy hôm qua")
        self.button_refresh_form = QPushButton("Làm mới form")
        self.button_save_draft.clicked.connect(self.save_current_attendance_as_draft)
        self.button_finalize_day.clicked.connect(self.finalize_current_attendance)
        self.button_copy_yesterday.clicked.connect(lambda: self.show_placeholder_message("Copy hôm qua"))
        self.button_refresh_form.clicked.connect(self.reset_attendance_form)
        for button in [self.button_save_draft, self.button_finalize_day, self.button_copy_yesterday, self.button_refresh_form]:
            action_layout.addWidget(button)
        action_layout.addStretch()

        right_layout.addWidget(common_group)
        right_layout.addWidget(self.absent_checkbox)
        right_layout.addWidget(self.status_hint_frame)
        right_layout.addWidget(self.blow_group)
        right_layout.addWidget(self.cut_group)
        right_layout.addLayout(action_layout)
        right_layout.addStretch()

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 6)
        layout.addWidget(splitter)
        return tab

    def build_tab_reports(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        filter_group = QGroupBox("Bộ lọc báo cáo kỳ công")
        filter_layout = QHBoxLayout(filter_group)
        self.report_team_combo = QComboBox()
        self.report_team_combo.addItems(["Tổ thổi", "Tổ cắt"])
        self.report_period_combo = QComboBox()
        self.report_period_combo.addItems(self.report_periods)
        self.button_view_report = QPushButton("Xem báo cáo")
        self.button_export_excel = QPushButton("Xuất Excel")
        self.button_print_report = QPushButton("In bảng công")
        self.button_view_report.clicked.connect(self.refresh_report_table)
        self.report_team_combo.currentIndexChanged.connect(self.refresh_report_table)
        self.report_period_combo.currentIndexChanged.connect(self.refresh_report_table)
        self.button_export_excel.clicked.connect(lambda: self.show_placeholder_message("Xuất Excel"))
        self.button_print_report.clicked.connect(lambda: self.show_placeholder_message("In bảng công"))
        filter_layout.addWidget(QLabel("Tổ"))
        filter_layout.addWidget(self.report_team_combo)
        filter_layout.addWidget(QLabel("Kỳ công"))
        filter_layout.addWidget(self.report_period_combo)
        filter_layout.addWidget(self.button_view_report)
        filter_layout.addWidget(self.button_export_excel)
        filter_layout.addWidget(self.button_print_report)
        filter_layout.addStretch()

        self.report_hint_label = QLabel()
        self.report_hint_label.setWordWrap(True)

        self.report_header_scroll = QScrollArea()
        self.report_header_scroll.setWidgetResizable(False)
        self.report_header_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.report_header_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.report_header_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.report_header_scroll.setStyleSheet("background-color: #fbf7f1;")
        self.report_header_widget = QWidget()
        self.report_header_widget.setStyleSheet("background-color: #fbf7f1;")
        self.report_header_layout = QVBoxLayout(self.report_header_widget)
        self.report_header_layout.setContentsMargins(0, 0, 0, 0)
        self.report_header_layout.setSpacing(0)
        self.report_header_top_row = QHBoxLayout()
        self.report_header_top_row.setContentsMargins(0, 0, 0, 0)
        self.report_header_top_row.setSpacing(0)
        self.report_header_bottom_row = QHBoxLayout()
        self.report_header_bottom_row.setContentsMargins(0, 0, 0, 0)
        self.report_header_bottom_row.setSpacing(0)
        self.report_header_layout.addLayout(self.report_header_top_row)
        self.report_header_layout.addLayout(self.report_header_bottom_row)
        self.report_header_scroll.setWidget(self.report_header_widget)

        self.report_table = QTableWidget()
        self.report_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.report_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.report_table.verticalHeader().setVisible(False)
        self.report_table.horizontalHeader().setVisible(False)
        self.report_table.setWordWrap(False)
        self.report_table.setStyleSheet("QTableWidget { gridline-color: #b9ad9c; }")
        self.report_table.horizontalScrollBar().valueChanged.connect(self._sync_report_header_scroll)

        summary_group = QGroupBox("Tổng hợp kỳ công")
        summary_layout = QGridLayout(summary_group)
        self.summary_total_employees = QLabel("0")
        self.summary_total_days = QLabel("0")
        self.summary_total_amount = QLabel("0")
        summary_layout.addWidget(QLabel("Tổng nhân viên"), 0, 0)
        summary_layout.addWidget(self.summary_total_employees, 0, 1)
        summary_layout.addWidget(QLabel("Tổng công"), 0, 2)
        summary_layout.addWidget(self.summary_total_days, 0, 3)
        summary_layout.addWidget(QLabel("Tổng tiền"), 0, 4)
        summary_layout.addWidget(self.summary_total_amount, 0, 5)
        summary_layout.setColumnStretch(6, 1)

        layout.addWidget(filter_group)
        layout.addWidget(self.report_hint_label)
        layout.addWidget(self.report_header_scroll)
        layout.addWidget(self.report_table, 1)
        layout.addWidget(summary_group)
        return tab

    def build_tab_settings(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)

        blow_group = QGroupBox("Cấu hình việc tổ thổi")
        blow_layout = QVBoxLayout(blow_group)
        self.settings_blow_table = QTableWidget(0, 4)
        self.settings_blow_table.setHorizontalHeaderLabels(["Tên việc", "Kiểu nhập", "Đơn giá", "Trạng thái"])
        self.settings_blow_table.verticalHeader().setVisible(False)
        self.settings_blow_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.settings_blow_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.settings_blow_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.settings_blow_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.settings_blow_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        blow_layout.addWidget(self.settings_blow_table)

        cut_group = QGroupBox("Cấu hình loại bao tổ cắt")
        cut_layout = QVBoxLayout(cut_group)
        self.settings_cut_table = QTableWidget(0, 3)
        self.settings_cut_table.setHorizontalHeaderLabels(["Loại bao", "Đơn giá", "Trạng thái"])
        self.settings_cut_table.verticalHeader().setVisible(False)
        self.settings_cut_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.settings_cut_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.settings_cut_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.settings_cut_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        cut_layout.addWidget(self.settings_cut_table)

        layout.addWidget(blow_group)
        layout.addWidget(cut_group)
        layout.addStretch()
        return tab

    def reload_all_ui_data(self) -> None:
        selected_management_id = self.get_selected_employee_management_id()
        selected_attendance_id = self.get_selected_attendance_employee_id()
        self.load_employees_from_db()
        self.load_reference_data_from_db()
        self.load_report_periods_from_db()
        self.load_attendance_statuses_for_selected_date()
        self.refresh_employee_table()
        self.refresh_attendance_employee_table()
        self.refresh_settings_tables()
        self.refresh_report_table()
        self.restore_management_employee_selection(selected_management_id)
        self.restore_attendance_employee_selection(selected_attendance_id)

    def load_employees_from_db(self) -> None:
        with self.SessionLocal() as session:
            rows = session.scalars(select(Employee).order_by(Employee.team, Employee.name)).all()
            self.employees = [
                {
                    "id": employee.id,
                    "name": employee.name,
                    "team": self._team_to_label(employee.team),
                    "active": employee.is_active,
                    "shift": "-",
                }
                for employee in rows
            ]

    def load_report_periods_from_db(self) -> None:
        with self.SessionLocal() as session:
            periods = session.scalars(select(Period).order_by(Period.start_date)).all()
        self.report_periods = [self._format_period_label(period) for period in periods]
        if hasattr(self, "report_period_combo"):
            current_text = self.report_period_combo.currentText()
            self.report_period_combo.blockSignals(True)
            self.report_period_combo.clear()
            self.report_period_combo.addItems(self.report_periods)
            if current_text:
                index = self.report_period_combo.findText(current_text)
                if index >= 0:
                    self.report_period_combo.setCurrentIndex(index)
            self.report_period_combo.blockSignals(False)

    def _format_period_label(self, period: Period) -> str:
        return f"Kì {period.start_date.strftime('%d/%m/%Y')} - {period.end_date.strftime('%d/%m/%Y')}"

    def _report_work_values_for_record(self, team_key: str, record: DailyRecord | None) -> dict[str, str]:
        if record is None or record.is_absent:
            return {}
        if team_key == "blow":
            values: dict[str, str] = {}
            for work_log in record.work_logs:
                label = self._work_code(work_log.work_type.name)
                if work_log.work_type.input_type == WorkInputType.TICK:
                    values[label] = "1"
                else:
                    values[label] = str(work_log.quantity)
            return values

        values = {}
        for cut_log in record.cut_logs:
            label = self._abbreviate_cut_report_label(cut_log.bag_type.name)
            values[label] = str(cut_log.quantity)
        return values

    def _report_amount_for_record(self, record: DailyRecord | None) -> int:
        if record is None or record.is_absent:
            return 0
        work_total = sum(int(work_log.amount_snapshot or 0) for work_log in record.work_logs)
        cut_total = sum(int(cut_log.amount_snapshot or 0) for cut_log in record.cut_logs)
        return work_total + cut_total

    def get_selected_attendance_date(self) -> date:
        selected_qdate = self.attendance_date_edit.date()
        return date(selected_qdate.year(), selected_qdate.month(), selected_qdate.day())

    def on_attendance_date_changed(self, _selected_date: QDate) -> None:
        self.reload_attendance_for_selected_date()

    def reload_attendance_for_selected_date(self) -> None:
        selected_employee_id = self.get_selected_attendance_employee_id()
        selected_day = self.get_selected_attendance_date()
        self.label_selected_date.setText(self._format_attendance_date(selected_day))
        self.attendance_list_title_label.setText(f"Nhân viên ngày {self._format_attendance_date(selected_day)}")
        self.load_attendance_statuses_for_selected_date()
        self.refresh_attendance_employee_table()
        self.restore_attendance_employee_selection(selected_employee_id)

    def get_existing_daily_record_for_date(
        self, session: Session, employee_id: int, selected_day: date
    ) -> DailyRecord | None:
        return session.scalar(
            select(DailyRecord).where(
                DailyRecord.employee_id == employee_id,
                DailyRecord.date == selected_day,
            )
        )

    def get_shift_label_for_date(self, session: Session, employee_id: int, selected_day: date) -> str:
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

    def load_reference_data_from_db(self) -> None:
        with self.SessionLocal() as session:
            work_types = session.scalars(select(WorkType).order_by(WorkType.id)).all()
            self.blow_work_configs = [
                {
                    "name": work_type.name,
                    "code": self._work_code(work_type.name),
                    "input_type": "Số lượng" if work_type.input_type == WorkInputType.QUANTITY else "Tick",
                    "price_text": f"{work_type.unit_price:,}",
                    "active": "Đang dùng" if work_type.is_active else "Ngưng dùng",
                }
                for work_type in work_types
            ]
            bag_types = session.scalars(select(BagType).order_by(BagType.id)).all()
            self.cut_bag_types = [
                {"name": bag_type.name, "price": bag_type.unit_price, "active": "Đang dùng" if bag_type.is_active else "Ngưng dùng"}
                for bag_type in bag_types
            ]

        if hasattr(self, "blow_rows_layout"):
            self.rebuild_blow_rows()

    def load_attendance_statuses_for_selected_date(self) -> None:
        selected_day = self.get_selected_attendance_date()
        with self.SessionLocal() as session:
            records = session.scalars(select(DailyRecord).where(DailyRecord.date == selected_day)).all()
            status_map = {}
            for record in records:
                status_map[record.employee_id] = self._attendance_status_from_record(record)
        self.attendance_status_map = status_map

    def refresh_employee_table(self) -> None:
        keyword = self.employee_search_input.text().strip().lower() if hasattr(self, "employee_search_input") else ""
        filtered = [employee for employee in self.employees if keyword in employee["name"].lower()]
        self.employee_table.setRowCount(len(filtered))
        for row, employee in enumerate(filtered):
            self._set_table_item(self.employee_table, row, 0, employee["name"], employee["id"])
            self._set_table_item(self.employee_table, row, 1, employee["team"])
            self._set_table_item(self.employee_table, row, 2, "Đang làm" if employee["active"] else "Ngưng sử dụng")

    def refresh_attendance_employee_table(self) -> None:
        active_employees = [employee for employee in self.employees if employee["active"]]
        self.attendance_employee_table.setRowCount(len(active_employees))
        for row, employee in enumerate(active_employees):
            self._set_table_item(self.attendance_employee_table, row, 0, employee["name"], employee["id"])
            self._set_table_item(self.attendance_employee_table, row, 1, employee["team"])
            self._set_table_item(self.attendance_employee_table, row, 2, self.attendance_status_map.get(employee["id"], "Chưa chấm"))

    def update_attendance_form_for_selected_employee(self) -> None:
        employee = self.get_selected_attendance_employee()
        selected_day = self.get_selected_attendance_date()
        self.label_selected_date.setText(self._format_attendance_date(selected_day))
        if employee is None:
            self.current_daily_record_id = None
            self.selected_employee_id = None
            self.label_selected_employee.setText("-")
            self.label_selected_team.setText("-")
            self.label_selected_shift.setText("-")
            self.label_record_status.setText("-")
            self.blow_group.setVisible(False)
            self.cut_group.setVisible(False)
            self._update_status_hint("-")
            return

        self.selected_employee_id = employee["id"]
        self.label_selected_employee.setText(employee["name"])
        self.label_selected_team.setText(employee["team"])
        self.reset_attendance_form_controls()

        is_blow_team = employee["team"] == "Tổ thổi"
        self.blow_group.setVisible(is_blow_team)
        self.cut_group.setVisible(not is_blow_team)

        with self.SessionLocal() as session:
            self.label_selected_shift.setText(self.get_shift_label_for_date(session, employee["id"], selected_day))
            record = self.get_existing_daily_record_for_date(session, employee["id"], selected_day)
            if record is None:
                self.current_daily_record_id = None
                self.current_daily_record_status = "Chưa chấm"
                self.label_record_status.setText("Chưa chấm")
                self.absent_checkbox.setChecked(False)
                self.apply_absent_checkbox_state(False)
                self._update_status_hint("Chưa chấm", is_absent=False)
                return

            self.current_daily_record_id = record.id
            self.current_daily_record_status = self._attendance_status_from_record(record)
            self.label_record_status.setText(self.current_daily_record_status)
            self._update_status_hint(self.current_daily_record_status, is_absent=record.is_absent)
            self.load_daily_record_into_form(session, record)

    def load_daily_record_into_form(self, session: Session, record: DailyRecord) -> None:
        self.absent_checkbox.setChecked(record.is_absent)
        self.apply_absent_checkbox_state(record.is_absent)
        if record.is_absent:
            return

        for work_log in record.work_logs:
            work_name = work_log.work_type.name
            if work_name in self.blow_quantity_controls:
                controls = self.blow_quantity_controls[work_name]
                checkbox = controls["checkbox"]
                spinbox = controls["spinbox"]
                assert isinstance(checkbox, QCheckBox)
                assert isinstance(spinbox, QSpinBox)
                checkbox.setChecked(True)
                spinbox.setValue(work_log.quantity)
            elif work_name in self.blow_glove_checkboxes:
                self.blow_glove_checkboxes[work_name].setChecked(True)

        if record.cut_logs:
            self.cut_table.setRowCount(0)
            for cut_log in record.cut_logs:
                self.add_cut_row()
                row = self.cut_table.rowCount() - 1
                bag_combo = self.cut_table.cellWidget(row, 0)
                quantity_spin = self.cut_table.cellWidget(row, 1)
                if isinstance(bag_combo, QComboBox):
                    index = bag_combo.findText(cut_log.bag_type.name)
                    if index >= 0:
                        bag_combo.setCurrentIndex(index)
                if isinstance(quantity_spin, QSpinBox):
                    quantity_spin.setValue(cut_log.quantity)

    def save_current_attendance_as_draft(self) -> None:
        self._persist_current_attendance(finalize=False)

    def finalize_current_attendance(self) -> None:
        self._persist_current_attendance(finalize=True)

    def _persist_current_attendance(self, finalize: bool) -> None:
        employee = self.get_selected_attendance_employee()
        if employee is None:
            QMessageBox.warning(self, "Cảnh báo", "Vui lòng chọn nhân viên.")
            return

        selected_day = self.get_selected_attendance_date()

        if employee["team"] == "Tổ thổi":
            valid, message = self.validate_blow_form()
            if not valid:
                QMessageBox.warning(self, "Cảnh báo", message)
                return

        try:
            with self.SessionLocal() as session:
                self.ensure_period_for_date(session, selected_day)
                record = get_or_create_daily_record(session, employee["id"], selected_day)
                if record.status == DailyRecordStatus.DONE:
                    record.status = DailyRecordStatus.DRAFT
                    session.flush()

                record.work_logs.clear()
                record.cut_logs.clear()
                session.flush()

                if self.absent_checkbox.isChecked():
                    set_daily_record_absent(session, record.id, True)
                else:
                    set_daily_record_absent(session, record.id, False)
                    if employee["team"] == "Tổ thổi":
                        for work_type_id, quantity in self.collect_blow_form_data(session).items():
                            add_blow_work(session, record.id, work_type_id, quantity)
                    else:
                        for bag_type_id, quantity in self.collect_cut_form_data(session):
                            add_cut_work(session, record.id, bag_type_id, quantity)

                record.status = DailyRecordStatus.DONE if finalize else DailyRecordStatus.DRAFT
                session.flush()

                session.commit()
        except (ValidationError, LockedPeriodError, NotFoundError) as exc:
            QMessageBox.warning(self, "Cảnh báo", self._translate_attendance_error(exc))
            return

        self.load_attendance_statuses_for_selected_date()
        self.refresh_attendance_employee_table()
        self.update_attendance_form_for_selected_employee()
        self.load_report_periods_from_db()
        self.refresh_report_table()
        saved_date = self._format_attendance_date(selected_day)
        message = (
            f"Đã lưu nháp chấm công ngày {saved_date}."
            if not finalize
            else f"Đã lưu chấm công ngày {saved_date}."
        )
        QMessageBox.information(self, "Thông báo", message)

    def collect_blow_form_data(self, session: Session) -> dict[int, int | None]:
        name_to_id = {
            work_type.name: work_type.id
            for work_type in session.scalars(select(WorkType).where(WorkType.is_active.is_(True))).all()
        }
        payload: dict[int, int | None] = {}
        for work_name, controls in self.blow_quantity_controls.items():
            checkbox = controls["checkbox"]
            spinbox = controls["spinbox"]
            assert isinstance(checkbox, QCheckBox)
            assert isinstance(spinbox, QSpinBox)
            if checkbox.isChecked():
                payload[name_to_id[work_name]] = spinbox.value()
        for work_name, checkbox in self.blow_glove_checkboxes.items():
            if checkbox.isChecked():
                payload[name_to_id[work_name]] = None
        return payload

    def collect_cut_form_data(self, session: Session) -> list[tuple[int, int]]:
        name_to_id = {bag_type.name: bag_type.id for bag_type in session.scalars(select(BagType)).all()}
        rows: list[tuple[int, int]] = []
        for row in range(self.cut_table.rowCount()):
            bag_combo = self.cut_table.cellWidget(row, 0)
            quantity_spin = self.cut_table.cellWidget(row, 1)
            if isinstance(bag_combo, QComboBox) and isinstance(quantity_spin, QSpinBox):
                bag_name = bag_combo.currentText()
                quantity = quantity_spin.value()
                if bag_name and quantity > 0:
                    rows.append((name_to_id[bag_name], quantity))
        return rows

    def refresh_report_table(self) -> None:
        if not hasattr(self, "report_table"):
            return

        team_label = self.report_team_combo.currentText()
        period_label = self.report_period_combo.currentText()
        render_model = self._build_report_render_model(team_label, period_label)
        columns = render_model["columns"]
        rows = render_model["rows"]

        self.report_table.clearContents()
        self.report_table.setRowCount(len(rows))
        self.report_table.setColumnCount(len(columns))

        header = self.report_table.horizontalHeader()
        for column_index in range(len(columns)):
            header.setSectionResizeMode(column_index, QHeaderView.ResizeMode.Fixed)

        for row_index, row_data in enumerate(rows):
            values = row_data["values"]
            for column_index, column_meta in enumerate(columns):
                text = values[column_index] if column_index < len(values) else ""
                item = self._build_report_table_item(
                    text,
                    alignment=self._report_alignment_for_column(column_meta),
                    tooltip=self._report_tooltip_for_cell(column_meta, text),
                )
                self.report_table.setItem(row_index, column_index, item)
            self._shade_report_row(
                row_index,
                QColor("#f6efe6" if render_model["team_key"] == "blow" else "#eef4ea"),
            )

        self.report_table.resizeRowsToContents()
        self.report_table.resizeColumnsToContents()
        self._apply_report_column_widths(columns)
        self._rebuild_report_header(render_model)
        self._sync_report_header_scroll(self.report_table.horizontalScrollBar().value())

        self.summary_total_employees.setText(str(render_model["employee_count"]))
        self.summary_total_days.setText(str(render_model["total_workdays"]))
        self.summary_total_amount.setText(self._format_money(render_model["total_amount"]))
        self.report_hint_label.setText(
            f"Bảng công kì {period_label} hiển thị theo từng ngày nhân viên của {team_label.lower()}."
        )

    def _build_report_render_model(self, team_label: str, period_label: str) -> dict[str, object]:
        if not period_label:
            return {
                "team_key": self._report_team_key(team_label),
                "employee_count": 0,
                "employee_groups": [],
                "columns": [{"kind": "date", "label": "Ngày"}, {"kind": "day_total", "label": "Tổng tiền cả ngày"}],
                "rows": [],
                "total_amount": 0,
                "total_workdays": 0,
            }

        team_key = self._report_team_key(team_label)
        start_date, end_date = self._parse_report_period_bounds(period_label)
        visible_end_date = min(end_date, date.today())
        visible_dates = self._daterange(start_date, visible_end_date) if visible_end_date >= start_date else []
        team_enum = Team.CUT if team_key == "cut" else Team.BLOW

        with self.SessionLocal() as session:
            employee_ids_with_records = set(
                session.scalars(
                    select(DailyRecord.employee_id)
                    .join(Employee, Employee.id == DailyRecord.employee_id)
                    .where(
                        Employee.team == team_enum,
                        DailyRecord.date >= start_date,
                        DailyRecord.date <= end_date,
                    )
                ).all()
            )

            employees_query = select(Employee).where(Employee.team == team_enum)
            if employee_ids_with_records:
                employees_query = employees_query.where(
                    (Employee.is_active.is_(True)) | (Employee.id.in_(employee_ids_with_records))
                )
            else:
                employees_query = employees_query.where(Employee.is_active.is_(True))
            employees = session.scalars(employees_query.order_by(Employee.name)).all()
            employee_ids = [employee.id for employee in employees]

            if employee_ids:
                records = session.scalars(
                    select(DailyRecord)
                    .where(
                        DailyRecord.employee_id.in_(employee_ids),
                        DailyRecord.date >= start_date,
                        DailyRecord.date <= visible_end_date,
                    )
                    .options(
                        selectinload(DailyRecord.work_logs).selectinload(WorkLog.work_type),
                        selectinload(DailyRecord.cut_logs).selectinload(CutLog.bag_type),
                    )
                ).all()
            else:
                records = []

        record_by_employee_day = {(record.employee_id, record.date): record for record in records}

        employee_groups: list[dict[str, object]] = []
        columns: list[dict[str, object]] = [{"kind": "date", "label": "Ngày"}]
        for employee in employees:
            visible_work_labels = self._visible_report_subcolumns(team_key, employee.id, record_by_employee_day, visible_dates)
            group_columns = [*visible_work_labels, "Tổng"]
            employee_groups.append(
                {
                    "employee_id": employee.id,
                    "employee_name": employee.name,
                    "work_labels": visible_work_labels,
                    "columns": group_columns,
                }
            )
            for subcolumn in group_columns:
                columns.append(
                    {
                        "kind": "employee_total" if subcolumn == "Tổng" else "employee_value",
                        "employee_name": employee.name,
                        "label": subcolumn,
                    }
                )
        columns.append({"kind": "day_total", "label": "Tổng tiền cả ngày"})

        rows: list[dict[str, object]] = []
        total_amount = 0
        total_workdays = 0
        for current_day in visible_dates:
            rendered_values = [current_day.strftime("%d/%m")]
            row_total = 0
            for group in employee_groups:
                record = record_by_employee_day.get((group["employee_id"], current_day))
                work_values = self._report_work_values_for_record(team_key, record)
                amount = self._report_amount_for_record(record)
                for subcolumn in group["work_labels"]:
                    rendered_values.append(work_values.get(subcolumn, ""))
                rendered_values.append(self._format_money(amount))
                row_total += amount
                if amount > 0:
                    total_workdays += 1
            rendered_values.append(self._format_money(row_total))
            total_amount += row_total
            rows.append({"values": rendered_values})

        return {
            "team_key": team_key,
            "employee_count": len(employee_groups),
            "employee_groups": employee_groups,
            "columns": columns,
            "rows": rows,
            "total_amount": total_amount,
            "total_workdays": total_workdays,
        }

    def _report_team_key(self, team_label: str) -> str:
        lowered = team_label.casefold()
        return "cut" if "cắt" in lowered or "c?t" in lowered or "cut" in lowered else "blow"

    def _filter_visible_report_rows(
        self,
        period_label: str,
        rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        start_date, end_date = self._parse_report_period_bounds(period_label)
        visible_end_date = min(end_date, date.today())
        if visible_end_date < start_date:
            return []
        visible_labels = {
            current_day.strftime("%d/%m")
            for current_day in self._daterange(start_date, visible_end_date)
        }
        return [row_data for row_data in rows if str(row_data.get("date", "")) in visible_labels]

    def _parse_report_period_bounds(self, period_label: str) -> tuple[date, date]:
        parts = [int(value) for value in re.findall(r"\d+", period_label)]
        return date(parts[2], parts[1], parts[0]), date(parts[5], parts[4], parts[3])

    def _daterange(self, start_date: date, end_date: date) -> list[date]:
        days: list[date] = []
        current_day = start_date
        while current_day <= end_date:
            days.append(current_day)
            current_day += timedelta(days=1)
        return days

    def _visible_report_subcolumns(
        self,
        team_key: str,
        employee_id: int,
        record_by_employee_day: dict[tuple[int, date], DailyRecord],
        visible_dates: list[date],
    ) -> list[str]:
        used_labels: set[str] = set()
        for current_day in visible_dates:
            record = record_by_employee_day.get((employee_id, current_day))
            if record is None or record.is_absent:
                continue
            work_values = self._report_work_values_for_record(team_key, record)
            for label, raw_value in work_values.items():
                if self._has_report_work_value(raw_value):
                    used_labels.add(str(label))

        if team_key == "blow":
            ordered_labels = ["TM", "MN", "MT", "PC", "PG1", "PG2"]
        else:
            ordered_labels = self._cut_report_column_order(record_by_employee_day, visible_dates)
        return [label for label in ordered_labels if label in used_labels]

    def _cut_report_column_order(
        self,
        record_by_employee_day: dict[tuple[int, date], DailyRecord],
        visible_dates: list[date],
    ) -> list[str]:
        ordered_labels: list[str] = []
        seen_labels: set[str] = set()

        for bag_type in self.cut_bag_types:
            label = self._abbreviate_cut_report_label(str(bag_type.get("name", "")))
            if label and label not in seen_labels:
                ordered_labels.append(label)
                seen_labels.add(label)

        for current_day in visible_dates:
            for record in record_by_employee_day.values():
                if record.date != current_day or record.is_absent:
                    continue
                for cut_log in record.cut_logs:
                    label = self._abbreviate_cut_report_label(cut_log.bag_type.name)
                    if label not in seen_labels:
                        ordered_labels.append(label)
                        seen_labels.add(label)
        return ordered_labels

    def _abbreviate_cut_report_label(self, bag_type_name: str) -> str:
        for token in bag_type_name.replace("-", " ").split():
            lowered = token.casefold()
            if lowered.endswith("kg"):
                return token
            if token.upper() == "PP":
                return "PP"
        return bag_type_name.replace("Bao", "").strip()

    def _has_report_work_value(self, raw_value: object) -> bool:
        if isinstance(raw_value, bool):
            return raw_value
        if raw_value is None:
            return False
        if isinstance(raw_value, (int, float)):
            return raw_value != 0
        return str(raw_value).strip() != ""

    def _format_report_work_value(self, raw_value: object) -> str:
        if isinstance(raw_value, bool):
            return "1" if raw_value else ""
        if raw_value in (None, "", 0):
            return ""
        return str(raw_value)

    def _build_report_table_item(
        self,
        text: str,
        *,
        alignment: Qt.AlignmentFlag,
        tooltip: str = "",
    ) -> QTableWidgetItem:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setTextAlignment(alignment)
        item.setToolTip(tooltip)
        return item

    def _report_alignment_for_column(self, column_meta: dict[str, object]) -> Qt.AlignmentFlag:
        if column_meta["kind"] in {"employee_total", "day_total"}:
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        return Qt.AlignmentFlag.AlignCenter

    def _report_tooltip_for_cell(self, column_meta: dict[str, object], text: str) -> str:
        if column_meta["kind"] == "day_total" and text:
            return f"Tổng tiền cả ngày: {text}"
        return ""

    def _apply_report_column_widths(self, columns: list[dict[str, object]]) -> None:
        metrics = QFontMetrics(self.report_table.font())
        for column_index, column_meta in enumerate(columns):
            kind = str(column_meta["kind"])
            content_width = self.report_table.columnWidth(column_index)
            label_width = metrics.horizontalAdvance(str(column_meta.get("label", "")))
            if kind == "date":
                width = max(68, content_width + 8)
            elif kind == "employee_value":
                width = min(max(40, label_width + 12), 54)
            elif kind == "employee_total":
                width = min(max(80, content_width + 4), 88)
            else:
                width = min(max(116, content_width + 6), 124)
            self.report_table.setColumnWidth(column_index, width)

    def _rebuild_report_header(self, render_model: dict[str, object]) -> None:
        self._clear_layout(self.report_header_top_row)
        self._clear_layout(self.report_header_bottom_row)
        self.report_header_top_labels = []
        self.report_header_bottom_labels = []

        columns = render_model["columns"]
        if not columns:
            self.report_header_widget.setFixedWidth(0)
            return

        self.report_header_top_labels.append(
            self._add_report_header_label(self.report_header_top_row, "Ngày", self.report_table.columnWidth(0), is_top_row=True)
        )
        self.report_header_bottom_labels.append(
            self._add_report_header_label(self.report_header_bottom_row, "", self.report_table.columnWidth(0), is_group_end=True)
        )

        column_index = 1
        for group in render_model["employee_groups"]:
            group_columns = list(group["columns"])
            column_widths = [
                self.report_table.columnWidth(column_index + offset)
                for offset in range(len(group_columns))
            ]
            group_width = sum(column_widths)
            name_width = QFontMetrics(self.report_table.font()).horizontalAdvance(str(group["employee_name"])) + 24
            if group_width < name_width and column_widths:
                extra_width = name_width - group_width
                last_column_index = column_index + len(group_columns) - 1
                new_last_width = self.report_table.columnWidth(last_column_index) + extra_width
                self.report_table.setColumnWidth(last_column_index, new_last_width)
                column_widths[-1] = new_last_width
                group_width = sum(column_widths)
            self.report_header_top_labels.append(
                self._add_report_header_label(
                    self.report_header_top_row,
                    str(group["employee_name"]),
                    group_width,
                    is_top_row=True,
                    is_group_end=True,
                )
            )
            for offset, subcolumn in enumerate(group_columns):
                self.report_header_bottom_labels.append(
                    self._add_report_header_label(
                        self.report_header_bottom_row,
                        str(subcolumn),
                        self.report_table.columnWidth(column_index + offset),
                        is_total_column=subcolumn == "Tổng",
                        is_group_end=offset == len(group_columns) - 1,
                    )
                )
            column_index += len(group_columns)

        last_width = self.report_table.columnWidth(len(columns) - 1)
        self.report_header_top_labels.append(
            self._add_report_header_label(
                self.report_header_top_row,
                "Tổng tiền cả ngày",
                last_width,
                is_top_row=True,
                is_group_end=True,
                is_total_column=True,
            )
        )
        self.report_header_bottom_labels.append(
            self._add_report_header_label(
                self.report_header_bottom_row,
                "",
                last_width,
                is_group_end=True,
                is_total_column=True,
            )
        )

        total_width = sum(self.report_table.columnWidth(index) for index in range(len(columns)))
        self.report_header_widget.setFixedWidth(total_width)
        self.report_header_widget.adjustSize()
        self.report_header_scroll.setFixedHeight(self.report_header_widget.sizeHint().height() + 2)

    def _add_report_header_label(
        self,
        layout: QHBoxLayout,
        text: str,
        width: int,
        *,
        is_top_row: bool = False,
        is_total_column: bool = False,
        is_group_end: bool = False,
    ) -> QLabel:
        label = QLabel(text)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setFixedWidth(width)
        label.setMinimumHeight(34 if is_top_row else 30)
        right_border = "2px solid #8d816f" if is_group_end else "1px solid #b9ad9c"
        background = "#e7d8c3" if is_top_row else "#f7f1e8"
        if is_total_column:
            background = "#eee4d5"
        label.setStyleSheet(
            "QLabel {"
            f"background-color: {background};"
            "border-top: 1px solid #b9ad9c;"
            "border-bottom: 1px solid #b9ad9c;"
            "border-left: 1px solid #b9ad9c;"
            f"border-right: {right_border};"
            "padding: 4px 6px;"
            "font-weight: 600;"
            "}"
        )
        layout.addWidget(label)
        return label

    def _sync_report_header_scroll(self, value: int) -> None:
        if hasattr(self, "report_header_scroll"):
            self.report_header_scroll.horizontalScrollBar().setValue(value)

    def _clear_layout(self, layout: QHBoxLayout | QVBoxLayout) -> None:
        while layout.count():
            child = layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()

    def _format_money(self, amount: int) -> str:
        return f"{amount:,}"

    def refresh_settings_tables(self) -> None:
        self.settings_blow_table.setRowCount(len(self.blow_work_configs))
        for row, item in enumerate(self.blow_work_configs):
            self._set_table_item(self.settings_blow_table, row, 0, item["name"])
            self._set_table_item(self.settings_blow_table, row, 1, item["input_type"])
            self._set_table_item(self.settings_blow_table, row, 2, item["price_text"])
            self._set_table_item(self.settings_blow_table, row, 3, item["active"])
        self.settings_cut_table.setRowCount(len(self.cut_bag_types))
        for row, item in enumerate(self.cut_bag_types):
            self._set_table_item(self.settings_cut_table, row, 0, item["name"])
            self._set_table_item(self.settings_cut_table, row, 1, f"{item['price']:,}")
            self._set_table_item(self.settings_cut_table, row, 2, item["active"])

    def rebuild_blow_rows(self) -> None:
        while self.blow_rows_layout.count():
            child = self.blow_rows_layout.takeAt(0)
            widget = child.widget()
            if widget is not None:
                widget.deleteLater()
        self.blow_quantity_controls.clear()
        self.blow_glove_checkboxes.clear()
        self._build_blow_rows()

    def _build_blow_rows(self) -> None:
        quantity_names = {item["name"] for item in self.blow_work_configs if item["input_type"] == "Số lượng"}
        for item in self.blow_work_configs:
            if item["name"] in quantity_names:
                self.blow_rows_layout.addWidget(self.build_blow_quantity_row(item["name"]))
            else:
                checkbox = QCheckBox(item["name"])
                checkbox.toggled.connect(lambda checked, name=item["name"]: self.on_glove_checkbox_changed(name, checked))
                self.blow_glove_checkboxes[item["name"]] = checkbox
                self.blow_rows_layout.addWidget(checkbox)
        self.blow_rows_layout.addStretch()

    def build_blow_quantity_row(self, work_name: str) -> QWidget:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        checkbox = QCheckBox(work_name)
        label = QLabel("Số lượng")
        spinbox = QSpinBox()
        spinbox.setRange(1, 100000)
        spinbox.setValue(1)
        label.setVisible(False)
        spinbox.setVisible(False)
        checkbox.toggled.connect(lambda checked, name=work_name: self.on_blow_quantity_checkbox_toggled(name, checked))
        row_layout.addWidget(checkbox)
        row_layout.addStretch()
        row_layout.addWidget(label)
        row_layout.addWidget(spinbox)
        self.blow_quantity_controls[work_name] = {"checkbox": checkbox, "label": label, "spinbox": spinbox}
        return row_widget

    def on_blow_quantity_checkbox_toggled(self, work_name: str, checked: bool) -> None:
        controls = self.blow_quantity_controls[work_name]
        label = controls["label"]
        spinbox = controls["spinbox"]
        assert isinstance(label, QLabel)
        assert isinstance(spinbox, QSpinBox)
        label.setVisible(checked)
        spinbox.setVisible(checked)
        if not checked:
            spinbox.setValue(1)

    def on_glove_checkbox_changed(self, selected_name: str, checked: bool) -> None:
        if not checked:
            return
        for glove_name, checkbox in self.blow_glove_checkboxes.items():
            if glove_name != selected_name and checkbox.isChecked():
                checkbox.blockSignals(True)
                checkbox.setChecked(False)
                checkbox.blockSignals(False)

    def validate_blow_form(self) -> tuple[bool, str]:
        if self.absent_checkbox.isChecked():
            return True, ""

        selected = False
        for work_name, controls in self.blow_quantity_controls.items():
            checkbox = controls["checkbox"]
            spinbox = controls["spinbox"]
            assert isinstance(checkbox, QCheckBox)
            assert isinstance(spinbox, QSpinBox)
            if checkbox.isChecked():
                selected = True
                if spinbox.value() <= 0:
                    return False, f"Số lượng của '{work_name}' phải lớn hơn 0."
        checked_gloves = [name for name, checkbox in self.blow_glove_checkboxes.items() if checkbox.isChecked()]
        if len(checked_gloves) > 1:
            return False, "Chỉ được chọn một mức Phụ găng trong cùng ngày."
        if checked_gloves:
            selected = True
        if not selected:
            return False, "Cần chọn ít nhất một việc tổ thổi."
        return True, ""

    def get_selected_attendance_employee(self) -> dict | None:
        current_row = self.attendance_employee_table.currentRow()
        if current_row < 0:
            return None
        item = self.attendance_employee_table.item(current_row, 0)
        if item is None:
            return None
        employee_id = item.data(Qt.ItemDataRole.UserRole)
        for employee in self.employees:
            if employee["id"] == employee_id:
                return employee
        return None

    def get_selected_attendance_employee_id(self) -> int | None:
        employee = self.get_selected_attendance_employee()
        if employee is None:
            return None
        return int(employee["id"])

    def get_selected_employee_from_management_table(self) -> dict | None:
        current_row = self.employee_table.currentRow()
        if current_row < 0:
            return None
        item = self.employee_table.item(current_row, 0)
        if item is None:
            return None
        employee_id = item.data(Qt.ItemDataRole.UserRole)
        for employee in self.employees:
            if employee["id"] == employee_id:
                return employee
        return None

    def get_selected_employee_management_id(self) -> int | None:
        employee = self.get_selected_employee_from_management_table()
        if employee is None:
            return None
        return int(employee["id"])

    def _bind_employee_management_buttons(self, tab: QWidget) -> None:
        management_buttons = tab.findChildren(QPushButton)[:3]
        for button, handler in zip(
            management_buttons,
            [self.add_employee, self.edit_employee, self.delete_employee],
            strict=False,
        ):
            try:
                button.clicked.disconnect()
            except TypeError:
                pass
            button.clicked.connect(handler)

    def add_employee(self) -> None:
        dialog = EmployeeDialog(self, title="Thêm nhân viên")
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        payload = dialog.get_form_data()
        name = str(payload["name"])
        team = self._label_to_team(str(payload["team_label"]))
        is_active = bool(payload["is_active"])

        if not name:
            QMessageBox.warning(self, "Thiếu dữ liệu", "Tên hiển thị không được để trống.")
            return

        with self.SessionLocal() as session:
            if self._employee_name_exists(session, name):
                QMessageBox.warning(self, "Tên bị trùng", "Tên hiển thị đã tồn tại. Vui lòng nhập tên khác.")
                return

            employee = Employee(name=name, team=team, is_active=is_active)
            session.add(employee)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                QMessageBox.warning(self, "Tên bị trùng", "Tên hiển thị đã tồn tại. Vui lòng nhập tên khác.")
                return

            employee_id = employee.id

        current_attendance_id = self.get_selected_attendance_employee_id()
        preferred_attendance_id = employee_id if is_active else current_attendance_id
        self.reload_all_ui_data()
        self.restore_management_employee_selection(employee_id)
        self.restore_attendance_employee_selection(preferred_attendance_id)
        QMessageBox.information(self, "Thành công", "Đã thêm nhân viên thành công")

    def edit_employee(self) -> None:
        selected_employee = self.get_selected_employee_from_management_table()
        if selected_employee is None:
            QMessageBox.warning(self, "Chưa chọn nhân viên", "Vui lòng chọn một nhân viên để sửa.")
            return

        dialog = EmployeeDialog(
            self,
            title="Sửa nhân viên",
            name=str(selected_employee["name"]),
            team_label=str(selected_employee["team"]),
            is_active=bool(selected_employee["active"]),
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        payload = dialog.get_form_data()
        name = str(payload["name"])
        team = self._label_to_team(str(payload["team_label"]))
        is_active = bool(payload["is_active"])

        if not name:
            QMessageBox.warning(self, "Thiếu dữ liệu", "Tên hiển thị không được để trống.")
            return

        employee_id = int(selected_employee["id"])
        with self.SessionLocal() as session:
            employee = session.get(Employee, employee_id)
            if employee is None:
                QMessageBox.warning(self, "Không tìm thấy", "Nhân viên này không còn tồn tại trong cơ sở dữ liệu.")
                return

            if self._employee_name_exists(session, name, exclude_employee_id=employee_id):
                QMessageBox.warning(self, "Tên bị trùng", "Tên hiển thị đã tồn tại. Vui lòng nhập tên khác.")
                return

            employee.name = name
            employee.team = team
            employee.is_active = is_active

            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                QMessageBox.warning(self, "Tên bị trùng", "Tên hiển thị đã tồn tại. Vui lòng nhập tên khác.")
                return

        current_attendance_id = self.get_selected_attendance_employee_id()
        preferred_attendance_id = employee_id if current_attendance_id == employee_id else current_attendance_id
        self.reload_all_ui_data()
        self.restore_management_employee_selection(employee_id)
        self.restore_attendance_employee_selection(preferred_attendance_id)
        QMessageBox.information(self, "Thành công", "Đã cập nhật nhân viên")

    def delete_employee(self) -> None:
        selected_employee = self.get_selected_employee_from_management_table()
        if selected_employee is None:
            QMessageBox.warning(self, "Chưa chọn nhân viên", "Vui lòng chọn một nhân viên để xóa.")
            return

        employee_id = int(selected_employee["id"])
        employee_name = str(selected_employee["name"])
        confirm = QMessageBox.question(
            self,
            "Xác nhận xóa",
            f"Bạn có chắc muốn xóa nhân viên '{employee_name}' không?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        deleted_without_history = True
        with self.SessionLocal() as session:
            employee = session.get(Employee, employee_id)
            if employee is None:
                QMessageBox.warning(self, "Không tìm thấy", "Nhân viên này không còn tồn tại trong cơ sở dữ liệu.")
                return

            has_history = (
                session.scalar(
                    select(DailyRecord.id).where(DailyRecord.employee_id == employee_id).limit(1)
                )
                is not None
            )
            if has_history:
                employee.is_active = False
                deleted_without_history = False
            else:
                session.delete(employee)

            session.commit()

        current_attendance_id = self.get_selected_attendance_employee_id()
        preferred_attendance_id = None if current_attendance_id == employee_id else current_attendance_id
        self.reload_all_ui_data()
        self.restore_management_employee_selection(None)
        self.restore_attendance_employee_selection(preferred_attendance_id)
        if current_attendance_id == employee_id:
            self.selected_employee_id = None
            self.current_daily_record_id = None

        if not deleted_without_history:
            QMessageBox.information(
                self,
                "Đã ngưng sử dụng",
                f"Nhân viên '{employee_name}' có lịch sử chấm công nên đã được chuyển sang trạng thái ngưng sử dụng.",
            )

    def _employee_name_exists(
        self, session: Session, name: str, exclude_employee_id: int | None = None
    ) -> bool:
        query = select(Employee.id).where(Employee.name == name)
        if exclude_employee_id is not None:
            query = query.where(Employee.id != exclude_employee_id)
        return session.scalar(query.limit(1)) is not None

    def restore_management_employee_selection(self, employee_id: int | None) -> bool:
        return self._restore_table_selection(self.employee_table, employee_id)

    def restore_attendance_employee_selection(self, employee_id: int | None) -> bool:
        restored = self._restore_table_selection(self.attendance_employee_table, employee_id)
        self.update_attendance_form_for_selected_employee()
        return restored

    def _restore_table_selection(self, table: QTableWidget, employee_id: int | None) -> bool:
        if employee_id is None:
            self._clear_table_selection(table)
            return False

        for row in range(table.rowCount()):
            item = table.item(row, 0)
            if item is None:
                continue
            if item.data(Qt.ItemDataRole.UserRole) == employee_id:
                table.selectRow(row)
                return True

        self._clear_table_selection(table)
        return False

    def _clear_table_selection(self, table: QTableWidget) -> None:
        selection_model = table.selectionModel()
        if selection_model is not None:
            selection_model.clearSelection()
            selection_model.setCurrentIndex(
                QModelIndex(),
                QItemSelectionModel.SelectionFlag.Clear,
            )

    def add_cut_row(self) -> None:
        row = self.cut_table.rowCount()
        self.cut_table.insertRow(row)
        bag_combo = QComboBox()
        bag_combo.addItems([item["name"] for item in self.cut_bag_types])
        quantity_spin = QSpinBox()
        quantity_spin.setRange(0, 100000)
        quantity_spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.cut_table.setCellWidget(row, 0, bag_combo)
        self.cut_table.setCellWidget(row, 1, quantity_spin)

    def remove_cut_row(self) -> None:
        current_row = self.cut_table.currentRow()
        if current_row >= 0:
            self.cut_table.removeRow(current_row)

    def reset_attendance_form(self) -> None:
        self.reset_attendance_form_controls()
        self.update_attendance_form_for_selected_employee()

    def reset_attendance_form_controls(self) -> None:
        self.absent_checkbox.blockSignals(True)
        self.absent_checkbox.setChecked(False)
        self.absent_checkbox.blockSignals(False)
        for controls in self.blow_quantity_controls.values():
            checkbox = controls["checkbox"]
            assert isinstance(checkbox, QCheckBox)
            checkbox.setChecked(False)
        for checkbox in self.blow_glove_checkboxes.values():
            checkbox.setChecked(False)
        self.cut_table.setRowCount(0)
        self.apply_absent_checkbox_state(False)

    def apply_absent_checkbox_state(self, is_absent: bool) -> None:
        self.blow_group.setDisabled(is_absent)
        self.cut_group.setDisabled(is_absent)

    def show_placeholder_message(self, action_name: str) -> None:
        QMessageBox.information(self, "Thông báo", f"Chức năng '{action_name}' đang ở chế độ mô phỏng.")

    def _update_status_hint(self, status: str, is_absent: bool = False) -> None:
        messages = {
            "Chưa chấm": "Bản ghi chưa được tạo. Có thể lưu nháp khi bắt đầu ca.",
            "Nháp": "Bản ghi đang ở trạng thái nháp. Có thể tiếp tục bổ sung dữ liệu và lưu lại.",
            "Đã lưu": "Bản ghi đã được lưu cho ngày đã chọn. Vẫn có thể mở lại và cập nhật.",
            "Nghỉ": "Nhân viên được đánh dấu nghỉ cho ngày đã chọn. Không cần nhập công việc.",
            "Thiếu số lượng": "Bản ghi còn thiếu sản lượng hoặc số lượng cuối ca.",
            "-": "Chọn nhân viên để bắt đầu tạo hoặc cập nhật bản ghi chấm công.",
        }
        self.status_hint_text.setText(messages.get(status, messages["-"]))
        warning = status == "Thiếu số lượng"
        self.status_warning_label.setVisible(warning)
        if warning:
            self.status_hint_frame.setStyleSheet("QFrame { background-color: #fff3cd; border: 1px solid #e0b84f; border-radius: 4px; } QLabel { color: #5f4700; }")
        elif is_absent and status == "Nghỉ":
            self.status_hint_frame.setStyleSheet("QFrame { background-color: #eef6ff; border: 1px solid #8ab3e6; border-radius: 4px; } QLabel { color: #1f4f82; }")
        elif status == "Đã lưu":
            self.status_hint_frame.setStyleSheet("QFrame { background-color: #edf7ed; border: 1px solid #9ac39a; border-radius: 4px; } QLabel { color: #285b2a; }")
        else:
            self.status_hint_frame.setStyleSheet("QFrame { background-color: #f5f5f5; border: 1px solid #d0d0d0; border-radius: 4px; } QLabel { color: #333333; }")

    def _attendance_status_from_record(self, record: DailyRecord) -> str:
        if record.is_absent:
            return "Nghỉ"
        if record.status == DailyRecordStatus.DONE:
            return "Đã lưu"
        return "Nháp"

    def _translate_attendance_error(self, exc: Exception) -> str:
        raw_message = str(exc)
        message_map = {
            "employee is inactive": "Nhân viên này đã ngưng sử dụng.",
            "no period found for date": "Không tìm thấy kỳ công phù hợp cho ngày đã chọn.",
            "cannot create record in locked period": "Ngày đã chọn thuộc kỳ công đã khóa nên không thể lưu.",
            "cannot modify daily record in a locked period": "Ngày đã chọn thuộc kỳ công đã khóa nên không thể cập nhật.",
            "Cannot add work to absent record": "Ngày này đang được đánh dấu nghỉ nên không thể nhập việc.",
            "cannot use both glove work types in the same daily record": "Chỉ được chọn một mức Phụ găng trong cùng ngày.",
            "blow team daily record must contain at least one work log": "Cần chọn ít nhất một việc cho tổ thổi.",
            "cut team daily record must contain at least one cut log": "Cần nhập ít nhất một dòng việc cho tổ cắt.",
        }
        return message_map.get(raw_message, raw_message)

    def _format_attendance_date(self, selected_day: date) -> str:
        return selected_day.strftime("%d/%m/%Y")

    def _team_to_label(self, team: Team) -> str:
        return "Tổ thổi" if team == Team.BLOW else "Tổ cắt"

    def _label_to_team(self, team_label: str) -> Team:
        return Team.BLOW if team_label == "Tổ thổi" else Team.CUT

    def _work_code(self, work_name: str) -> str:
        mapping = {
            "Thừa máy": "TM",
            "Máy nhỏ": "MN",
            "Máy to": "MT",
            "Phụ cắt": "PC",
            "Phụ găng 1 máy": "PG1",
            "Phụ găng 2 máy": "PG2",
        }
        return mapping.get(work_name, work_name)

    def _calculate_cycle_bounds(self, current_day: date) -> tuple[date, date]:
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

    def _shade_report_row(self, row: int, color: QColor) -> None:
        for column in range(self.report_table.columnCount()):
            item = self.report_table.item(row, column)
            if item is not None:
                item.setBackground(color)

    def _set_table_item(self, table: QTableWidget, row: int, column: int, text: str, user_data: object | None = None) -> None:
        item = QTableWidgetItem(text)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        if user_data is not None:
            item.setData(Qt.ItemDataRole.UserRole, user_data)
        table.setItem(row, column, item)


def main() -> int:
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
