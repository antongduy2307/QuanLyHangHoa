from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from modules.attendance.service import AttendanceDayEntryService, AttendanceEmployeeService
from modules.attendance.report_service import AttendanceReportService
from modules.attendance.ui.day_entry_tab import AttendanceDayEntryTab
from modules.attendance.ui.employee_tab import EmployeeManagementTab
from modules.attendance.ui.report_tab import AttendanceReportTab
from shared.widgets.ui_scale import apply_large_ui


class AttendancePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.employee_tab = EmployeeManagementTab(AttendanceEmployeeService())
        self.day_entry_tab = AttendanceDayEntryTab(AttendanceDayEntryService())
        self.report_tab = AttendanceReportTab(AttendanceReportService())
        self.employee_tab.employees_changed.connect(self.day_entry_tab.reload_for_current_date)
        self.tabs.currentChanged.connect(self._handle_current_tab_changed)
        self.tabs.addTab(self.employee_tab, "Nhân viên")
        self.tabs.addTab(self.day_entry_tab, "Chấm công")
        self.tabs.addTab(self.report_tab, "Báo cáo")
        layout.addWidget(self.tabs)
        apply_large_ui(self)

    def refresh_all(self) -> None:
        self.employee_tab.reload()
        self.day_entry_tab.reload_for_current_date()
        self.report_tab.reload_periods()

    def _handle_current_tab_changed(self, index: int) -> None:
        if self.tabs.widget(index) is self.day_entry_tab:
            self.day_entry_tab.reload_for_current_date()
        if self.tabs.widget(index) is self.report_tab:
            self.report_tab.reload_periods()

    def _build_placeholder_tab(self, message: str) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()
        return tab
