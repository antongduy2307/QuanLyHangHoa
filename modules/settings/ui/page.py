from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QFormLayout, QLabel, QPushButton, QWidget

from core.version import APP_VERSION
from modules.settings.service import SettingsService, UI_SCALE_OPTIONS, get_ui_scale_label


class SettingsPage(QWidget):
    ui_scale_changed = pyqtSignal(str)
    check_updates_requested = pyqtSignal()

    def __init__(self, service: SettingsService) -> None:
        super().__init__()
        self._service = service
        preferences = service.get_preferences()
        self._update_status_label = QLabel("Chưa kiểm tra cập nhật.")
        self._update_status_label.setWordWrap(True)
        self._check_updates_button = QPushButton("Kiểm tra cập nhật")
        self._check_updates_button.clicked.connect(self.check_updates_requested.emit)

        self._scale_combo = QComboBox()
        for key, label, _factor in UI_SCALE_OPTIONS:
            self._scale_combo.addItem(label, key)
        current_index = self._scale_combo.findData(preferences.ui_scale_preset)
        if current_index >= 0:
            self._scale_combo.setCurrentIndex(current_index)
        self._scale_combo.currentIndexChanged.connect(self._handle_scale_changed)

        layout = QFormLayout(self)
        layout.addRow("Tên ứng dụng", QLabel(preferences.app_name))
        layout.addRow("Phiên bản hiện tại", QLabel(APP_VERSION))
        layout.addRow("Thư mục export", QLabel(preferences.export_dir))
        layout.addRow("Thư mục backup", QLabel(preferences.backup_dir))
        layout.addRow("Cỡ giao diện", self._scale_combo)
        layout.addRow("Mặc định hiện tại", QLabel(get_ui_scale_label(preferences.ui_scale_preset)))
        layout.addRow("Cập nhật", self._check_updates_button)
        layout.addRow("Trạng thái cập nhật", self._update_status_label)

    def _handle_scale_changed(self) -> None:
        preset = str(self._scale_combo.currentData())
        self._service.set_ui_scale_preset(preset)
        self.ui_scale_changed.emit(preset)

    def set_update_busy(self, busy: bool, message: str | None = None) -> None:
        self._check_updates_button.setEnabled(not busy)
        if message:
            self._update_status_label.setText(message)

    def set_update_status(self, message: str) -> None:
        self._update_status_label.setText(message)
