from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QHBoxLayout, QLabel, QPushButton, QTabWidget, QVBoxLayout, QWidget

from core.version import APP_VERSION
from modules.settings.service import SettingsService, UI_SCALE_OPTIONS, get_ui_scale_label
from shared.widgets.ui_scale import apply_large_ui


class GeneralSettingsTab(QWidget):
    ui_scale_changed = pyqtSignal(str)
    check_updates_requested = pyqtSignal()
    backup_requested = pyqtSignal()
    open_logs_requested = pyqtSignal()
    export_diagnostics_requested = pyqtSignal()

    def __init__(self, service: SettingsService) -> None:
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

    def __init__(self, service: SettingsService) -> None:
        super().__init__()
        from modules.attendance.ui.settings_tab import AttendancePriceSettingsTab

        self.general_tab = GeneralSettingsTab(service)
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
