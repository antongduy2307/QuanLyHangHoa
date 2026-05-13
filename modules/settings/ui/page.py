from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.version import APP_VERSION
from modules.settings.service import SettingsService, UI_SCALE_OPTIONS, get_ui_scale_label
from shared.widgets.ui_scale import apply_large_ui


ISSUE_TYPE_LABELS = {
    "MISSING_EFFECTS_FOR_DONE_RECORD": "Thiếu cập nhật tồn kho",
    "STALE_EFFECTS_FOR_DRAFT_OR_ABSENT_RECORD": "Tồn kho còn hiệu lực cho bản ghi không còn chốt",
    "STALE_EFFECTS_FOR_MISSING_DAILY_RECORD": "Hiệu lực tồn kho không còn bản ghi chấm công",
    "QUANTITY_MISMATCH": "Lệch số lượng",
    "PRODUCT_MISMATCH": "Lệch mã hàng",
    "MISSING_PRODUCT_LINK": "Thiếu liên kết hàng hóa",
    "MISSING_MAIN_PRODUCT": "Không tìm thấy hàng hóa",
}


class AttendanceInventoryDiagnosticsPanel(QGroupBox):
    def __init__(self, diagnostic_service: Any | None = None) -> None:
        super().__init__("Kiểm tra tồn kho từ chấm công")
        if diagnostic_service is None:
            from modules.attendance.inventory_diagnostic_service import AttendanceInventoryDiagnosticService

            diagnostic_service = AttendanceInventoryDiagnosticService()
        self._diagnostic_service = diagnostic_service
        self._issues: list[Any] = []

        self.scan_button = QPushButton("Kiểm tra đồng bộ tồn kho chấm công")
        self.refresh_button = QPushButton("Làm mới")
        self.reconcile_button = QPushButton("Đồng bộ lại bản ghi này")
        self.reconcile_button.setEnabled(False)

        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        self.issues_table = QTableWidget(0, 7)
        self.issues_table.setHorizontalHeaderLabels(
            [
                "Ngày",
                "Nhân viên",
                "Loại lỗi",
                "Mức độ",
                "Mô tả",
                "Dữ liệu mong đợi",
                "Dữ liệu hiện tại",
            ]
        )
        self.issues_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.issues_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.issues_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.issues_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.issues_table.verticalHeader().setVisible(False)
        self.issues_table.itemSelectionChanged.connect(self._update_reconcile_button_state)

        actions = QHBoxLayout()
        actions.addWidget(self.scan_button)
        actions.addWidget(self.refresh_button)
        actions.addStretch(1)
        actions.addWidget(self.reconcile_button)

        layout = QVBoxLayout(self)
        layout.addLayout(actions)
        layout.addWidget(self.status_label)
        layout.addWidget(self.issues_table)

        self.scan_button.clicked.connect(self.scan_issues)
        self.refresh_button.clicked.connect(self.scan_issues)
        self.reconcile_button.clicked.connect(self._handle_reconcile_clicked)

    def scan_issues(self) -> None:
        try:
            issues = self._diagnostic_service.list_issues()
        except Exception as exc:  # pragma: no cover - exact DB errors vary by environment
            from shared.widgets.message_box import MessageBox

            MessageBox.error(self, "Không kiểm tra được tồn kho chấm công", str(exc))
            return
        self.set_issues(issues)

    def set_issues(self, issues: Sequence[Any]) -> None:
        self._issues = list(issues)
        self.issues_table.setRowCount(0)
        for row, issue in enumerate(self._issues):
            self.issues_table.insertRow(row)
            values = [
                "" if issue.work_date is None else str(issue.work_date),
                "" if issue.employee_id is None else str(issue.employee_id),
                self._issue_label(issue.issue_type),
                issue.severity,
                issue.message,
                issue.expected_lines_summary,
                issue.actual_effects_summary,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, row)
                self.issues_table.setItem(row, column, item)
        if self._issues:
            self.status_label.setText(f"Phát hiện {len(self._issues)} vấn đề đồng bộ tồn kho từ chấm công.")
        else:
            self.status_label.setText("Không phát hiện lệch tồn kho từ chấm công.")
        self._update_reconcile_button_state()

    def selected_issue(self) -> Any | None:
        selected_rows = self.issues_table.selectionModel().selectedRows()
        if not selected_rows:
            return None
        row = selected_rows[0].row()
        if row < 0 or row >= len(self._issues):
            return None
        return self._issues[row]

    def _handle_reconcile_clicked(self) -> None:
        issue = self.selected_issue()
        if issue is None:
            from shared.widgets.message_box import MessageBox

            MessageBox.warning(self, "Chưa chọn vấn đề", "Vui lòng chọn một dòng cần đồng bộ lại.")
            return
        if not self._can_reconcile(issue):
            from shared.widgets.message_box import MessageBox

            MessageBox.warning(
                self,
                "Không thể đồng bộ tự động",
                "Không thể tự đồng bộ vì bản ghi chấm công nguồn không còn tồn tại.",
            )
            return
        confirmed = (
            QMessageBox.question(
                self,
                "Xác nhận đồng bộ",
                "Bạn có chắc muốn đồng bộ lại tồn kho cho bản ghi chấm công này không?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )
        if not confirmed:
            return
        try:
            self._diagnostic_service.reconcile_daily_record(issue.daily_record_id)
        except Exception as exc:  # pragma: no cover - exact DB errors vary by environment
            from shared.widgets.message_box import MessageBox

            MessageBox.error(self, "Không đồng bộ được tồn kho chấm công", str(exc))
            return
        from shared.widgets.message_box import MessageBox

        MessageBox.info(self, "Đã đồng bộ", "Đã đồng bộ lại tồn kho cho bản ghi chấm công.")
        self.scan_issues()

    def _update_reconcile_button_state(self) -> None:
        issue = self.selected_issue()
        self.reconcile_button.setEnabled(issue is not None and self._can_reconcile(issue))

    def _can_reconcile(self, issue: Any) -> bool:
        return (
            issue.daily_record_id is not None
            and int(issue.daily_record_id) > 0
            and self._issue_type_value(issue.issue_type) != "STALE_EFFECTS_FOR_MISSING_DAILY_RECORD"
        )

    def _issue_label(self, issue_type: Any) -> str:
        issue_value = self._issue_type_value(issue_type)
        return ISSUE_TYPE_LABELS.get(issue_value, issue_value)

    def _issue_type_value(self, issue_type: Any) -> str:
        return str(getattr(issue_type, "value", issue_type))


class GeneralSettingsTab(QWidget):
    ui_scale_changed = pyqtSignal(str)
    check_updates_requested = pyqtSignal()
    backup_requested = pyqtSignal()
    open_logs_requested = pyqtSignal()
    export_diagnostics_requested = pyqtSignal()

    def __init__(self, service: SettingsService, *, diagnostic_service: Any | None = None) -> None:
        super().__init__()
        self._service = service
        preferences = service.get_preferences()
        self._current_scale_label = QLabel(get_ui_scale_label(preferences.ui_scale_preset))
        self._update_status_label = QLabel("Chưa kiểm tra cập nhật.")
        self._update_status_label.setWordWrap(True)
        self._check_updates_button = QPushButton("Kiểm tra cập nhật")
        self._check_updates_button.clicked.connect(self.check_updates_requested.emit)
        self._backup_button = QPushButton("Sao lưu dữ liệu")
        self._backup_button.clicked.connect(self.backup_requested.emit)
        self._open_logs_button = QPushButton("Mở thư mục log")
        self._open_logs_button.clicked.connect(self.open_logs_requested.emit)
        self._export_diagnostics_button = QPushButton("Xuất chẩn đoán")
        self._export_diagnostics_button.clicked.connect(self.export_diagnostics_requested.emit)
        self.attendance_inventory_diagnostics_panel = AttendanceInventoryDiagnosticsPanel(diagnostic_service)

        self._scale_combo = QComboBox()
        for key, label, _factor in UI_SCALE_OPTIONS:
            self._scale_combo.addItem(label, key)
        current_index = self._scale_combo.findData(preferences.ui_scale_preset)
        if current_index >= 0:
            self._scale_combo.setCurrentIndex(current_index)
        self._scale_combo.currentIndexChanged.connect(self._handle_scale_changed)

        diagnostics_actions = QHBoxLayout()
        diagnostics_actions.addWidget(self._open_logs_button)
        diagnostics_actions.addWidget(self._export_diagnostics_button)

        layout = QFormLayout(self)
        layout.addRow("Tên ứng dụng", QLabel(preferences.app_name))
        layout.addRow("Phiên bản hiện tại", QLabel(APP_VERSION))
        layout.addRow("Thư mục log", QLabel(preferences.log_dir))
        layout.addRow("Thư mục export", QLabel(preferences.export_dir))
        layout.addRow("Thư mục backup", QLabel(preferences.backup_dir))
        layout.addRow("Cỡ giao diện", self._scale_combo)
        layout.addRow("Mặc định hiện tại", self._current_scale_label)
        layout.addRow("Cập nhật", self._check_updates_button)
        layout.addRow("Trạng thái cập nhật", self._update_status_label)
        layout.addRow("Sao lưu", self._backup_button)
        layout.addRow("Chẩn đoán", diagnostics_actions)
        layout.addRow(self.attendance_inventory_diagnostics_panel)

    def _handle_scale_changed(self) -> None:
        preset = str(self._scale_combo.currentData())
        self._service.set_ui_scale_preset(preset)
        self._current_scale_label.setText(get_ui_scale_label(preset))
        self.ui_scale_changed.emit(preset)

    def set_update_busy(self, busy: bool, message: str | None = None) -> None:
        self._check_updates_button.setEnabled(not busy)
        if message:
            self._update_status_label.setText(message)

    def set_update_status(self, message: str) -> None:
        self._update_status_label.setText(message)

    def set_diagnostics_busy(self, busy: bool) -> None:
        self._open_logs_button.setEnabled(not busy)
        self._export_diagnostics_button.setEnabled(not busy)

    def set_backup_busy(self, busy: bool) -> None:
        self._backup_button.setEnabled(not busy)

    def apply_ui_scale_preset(self, preset: str) -> None:
        apply_large_ui(self, preset)
        current_index = self._scale_combo.findData(preset)
        if current_index >= 0 and current_index != self._scale_combo.currentIndex():
            self._scale_combo.blockSignals(True)
            self._scale_combo.setCurrentIndex(current_index)
            self._scale_combo.blockSignals(False)
        self._current_scale_label.setText(get_ui_scale_label(preset))


class SettingsPage(QWidget):
    ui_scale_changed = pyqtSignal(str)
    check_updates_requested = pyqtSignal()
    backup_requested = pyqtSignal()
    open_logs_requested = pyqtSignal()
    export_diagnostics_requested = pyqtSignal()
    attendance_config_changed = pyqtSignal()

    def __init__(self, service: SettingsService, *, diagnostic_service: Any | None = None) -> None:
        super().__init__()
        from modules.attendance.ui.settings_tab import AttendancePriceSettingsTab

        self.general_tab = GeneralSettingsTab(service, diagnostic_service=diagnostic_service)
        self.attendance_price_tab = AttendancePriceSettingsTab()
        self.tabs = QTabWidget()
        self.tabs.addTab(self.general_tab, "Cài đặt chung")
        self.tabs.addTab(self.attendance_price_tab, "Cài đặt giá chấm công")

        self.general_tab.ui_scale_changed.connect(self.ui_scale_changed.emit)
        self.general_tab.check_updates_requested.connect(self.check_updates_requested.emit)
        self.general_tab.backup_requested.connect(self.backup_requested.emit)
        self.general_tab.open_logs_requested.connect(self.open_logs_requested.emit)
        self.general_tab.export_diagnostics_requested.connect(self.export_diagnostics_requested.emit)
        self.attendance_price_tab.attendance_config_changed.connect(self.attendance_config_changed.emit)

        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)

    def set_update_busy(self, busy: bool, message: str | None = None) -> None:
        self.general_tab.set_update_busy(busy, message)

    def set_update_status(self, message: str) -> None:
        self.general_tab.set_update_status(message)

    def set_diagnostics_busy(self, busy: bool) -> None:
        self.general_tab.set_diagnostics_busy(busy)

    def set_backup_busy(self, busy: bool) -> None:
        self.general_tab.set_backup_busy(busy)

    def apply_ui_scale_preset(self, preset: str) -> None:
        self.general_tab.apply_ui_scale_preset(preset)
        apply_large_ui(self.attendance_price_tab, preset)

    def open_attendance_price_settings(self, first_incomplete_id: int | None = None) -> None:
        self.tabs.setCurrentWidget(self.attendance_price_tab)
        if hasattr(self.attendance_price_tab, "focus_first_incomplete_cut_work"):
            self.attendance_price_tab.focus_first_incomplete_cut_work(first_incomplete_id)
