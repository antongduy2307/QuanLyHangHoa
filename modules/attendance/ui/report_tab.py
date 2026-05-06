from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.exceptions import AppError
from modules.attendance.models import Team
from modules.attendance.report_service import AttendanceReportService, ReportPeriodOption, ReportRenderModel
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class AttendanceReportTab(QWidget):
    def __init__(self, service: AttendanceReportService) -> None:
        super().__init__()
        self._service = service
        self._periods: list[ReportPeriodOption] = []

        self.team_combo = QComboBox()
        self.team_combo.addItem("Tổ thổi", Team.BLOW.value)
        self.team_combo.addItem("Tổ cắt", Team.CUT.value)

        self.period_combo = QComboBox()
        self.view_button = QPushButton("Xem báo cáo")
        self.export_button = QPushButton("Xuất Excel")
        self.print_button = QPushButton("In bảng công")
        self.view_button.clicked.connect(self.refresh_report)
        self.export_button.clicked.connect(lambda: MessageBox.info(self, "Thông báo", "Xuất Excel sẽ được triển khai ở batch sau."))
        self.print_button.clicked.connect(lambda: MessageBox.info(self, "Thông báo", "In bảng công sẽ được triển khai ở batch sau."))

        self.employee_count_label = QLabel("Tổng nhân viên: 0")
        self.workdays_label = QLabel("Tổng ngày công có tiền: 0")
        self.total_amount_label = QLabel("Tổng tiền: 0")
        self.empty_label = QLabel("")
        self.empty_label.setWordWrap(True)

        self.table = QTableWidget(0, 0)
        configure_table_widget(self.table, "attendance.report.table")

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Tổ"))
        controls.addWidget(self.team_combo)
        controls.addWidget(QLabel("Kỳ"))
        controls.addWidget(self.period_combo, 1)
        controls.addWidget(self.view_button)
        controls.addWidget(self.export_button)
        controls.addWidget(self.print_button)

        summary = QHBoxLayout()
        summary.addWidget(self.employee_count_label)
        summary.addWidget(self.workdays_label)
        summary.addWidget(self.total_amount_label)
        summary.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(controls)
        layout.addLayout(summary)
        layout.addWidget(self.empty_label)
        layout.addWidget(self.table, 1)

        self.reload_periods()

    def reload_periods(self) -> None:
        selected_period_id = self.period_combo.currentData()
        self._periods = self._service.list_periods()
        self.period_combo.blockSignals(True)
        self.period_combo.clear()
        for period in self._periods:
            self.period_combo.addItem(period.label, period.id)
        if selected_period_id is not None:
            index = self.period_combo.findData(selected_period_id)
            if index >= 0:
                self.period_combo.setCurrentIndex(index)
        self.period_combo.blockSignals(False)
        self.view_button.setEnabled(bool(self._periods))
        self.empty_label.setText("" if self._periods else "Chưa có kỳ chấm công để xem báo cáo.")
        if self._periods:
            self.refresh_report()
        else:
            self._clear_report()

    def refresh_report(self) -> None:
        period_id = self.period_combo.currentData()
        if period_id is None:
            self._clear_report()
            self.empty_label.setText("Chưa có kỳ chấm công để xem báo cáo.")
            return
        try:
            model = self._service.build_report(team=str(self.team_combo.currentData()), period_id=int(period_id))
            self._render_report(model)
        except AppError as exc:
            MessageBox.error(self, "Không tải được báo cáo chấm công", str(exc))

    def _render_report(self, model: ReportRenderModel) -> None:
        self.empty_label.setText("" if model.rows else "Không có ngày nào trong kỳ cần hiển thị.")
        self.employee_count_label.setText(f"Tổng nhân viên: {model.employee_count}")
        self.workdays_label.setText(f"Tổng ngày công có tiền: {model.total_workdays}")
        self.total_amount_label.setText(f"Tổng tiền: {model.total_amount:,}")

        headers = self._flatten_headers(model)
        self.table.setColumnCount(len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setRowCount(len(model.rows))
        for row_index, row in enumerate(model.rows):
            for column_index, value in enumerate(row.values):
                item = QTableWidgetItem(value)
                if column_index > 0:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                self.table.setItem(row_index, column_index, item)

    def _flatten_headers(self, model: ReportRenderModel) -> list[str]:
        headers = ["Ngày"]
        for group in model.employee_groups:
            for column in group.columns:
                headers.append(f"{group.employee_name} - {column}")
        headers.append("Tổng tiền cả ngày")
        return headers

    def _clear_report(self) -> None:
        self.employee_count_label.setText("Tổng nhân viên: 0")
        self.workdays_label.setText("Tổng ngày công có tiền: 0")
        self.total_amount_label.setText("Tổng tiền: 0")
        self.table.setRowCount(0)
        self.table.setColumnCount(0)
