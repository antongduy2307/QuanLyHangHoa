from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QTabWidget, QVBoxLayout, QWidget

from modules.attendance.service import AttendanceEmployeeService
from modules.attendance.ui.employee_tab import EmployeeManagementTab
from shared.widgets.ui_scale import apply_large_ui


class AttendancePage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        tabs = QTabWidget()
        tabs.addTab(EmployeeManagementTab(AttendanceEmployeeService()), "Nhân viên")
        tabs.addTab(
            self._build_placeholder_tab("Module chấm công sẽ được port ở batch sau"),
            "Chấm công",
        )
        tabs.addTab(
            self._build_placeholder_tab("Module báo cáo chấm công sẽ được port ở batch sau"),
            "Báo cáo",
        )
        layout.addWidget(tabs)
        apply_large_ui(self)

    def _build_placeholder_tab(self, message: str) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        label = QLabel(message)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch()
        return tab
