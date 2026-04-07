from __future__ import annotations

from datetime import datetime, time

from PyQt6.QtCore import QDate, pyqtSignal
from PyQt6.QtWidgets import QComboBox, QDateEdit, QHBoxLayout, QPushButton, QWidget


class DateRangeSelectorWidget(QWidget):
    load_requested = pyqtSignal(str, object, object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.preset_combo = QComboBox()
        self.preset_combo.addItem("Hôm nay", "today")
        self.preset_combo.addItem("Hôm qua", "yesterday")
        self.preset_combo.addItem("7 ngày gần đây", "last_7_days")
        self.preset_combo.addItem("Tháng này", "this_month")
        self.preset_combo.addItem("Tháng trước", "last_month")
        self.preset_combo.addItem("Tùy chọn", "custom")

        current_date = QDate.currentDate()
        self.start_date_edit = QDateEdit(current_date)
        self.start_date_edit.setCalendarPopup(True)
        self.end_date_edit = QDateEdit(current_date)
        self.end_date_edit.setCalendarPopup(True)
        self.load_button = QPushButton("Xem báo cáo")

        layout = QHBoxLayout(self)
        layout.addWidget(self.preset_combo)
        layout.addWidget(self.start_date_edit)
        layout.addWidget(self.end_date_edit)
        layout.addWidget(self.load_button)

        self.preset_combo.currentIndexChanged.connect(self._sync_custom_visibility)
        self.load_button.clicked.connect(self._emit_load_requested)
        self._sync_custom_visibility()

    def sort_preset(self) -> str:
        return str(self.preset_combo.currentData())

    def custom_range(self) -> tuple[datetime, datetime]:
        start = self.start_date_edit.date().toPyDate()
        end = self.end_date_edit.date().toPyDate()
        return datetime.combine(start, time.min), datetime.combine(end, time.max)

    def _sync_custom_visibility(self) -> None:
        is_custom = self.sort_preset() == "custom"
        self.start_date_edit.setVisible(is_custom)
        self.end_date_edit.setVisible(is_custom)

    def _emit_load_requested(self) -> None:
        custom_start, custom_end = self.custom_range()
        self.load_requested.emit(self.sort_preset(), custom_start, custom_end)
