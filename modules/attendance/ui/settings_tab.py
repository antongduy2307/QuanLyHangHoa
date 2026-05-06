from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.exceptions import AppError
from modules.attendance.models import BagType, WorkInputType, WorkType
from modules.attendance.settings_service import AttendanceSettingsService
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


INPUT_TYPE_LABELS = {
    WorkInputType.QUANTITY: "Số lượng",
    WorkInputType.TICK: "Tick",
}


@dataclass(frozen=True, slots=True)
class WorkTypeFormValue:
    name: str
    input_type: WorkInputType
    unit_price: int


@dataclass(frozen=True, slots=True)
class BagTypeFormValue:
    name: str
    unit_price: int


class WorkTypeDialog(QDialog):
    deactivate_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, *, work_type: WorkType | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Công việc tổ thổi")
        self.work_type_id = None if work_type is None else work_type.id
        self.name_edit = QLineEdit()
        self.input_type_combo = QComboBox()
        self.input_type_combo.addItem(INPUT_TYPE_LABELS[WorkInputType.QUANTITY], WorkInputType.QUANTITY.value)
        self.input_type_combo.addItem(INPUT_TYPE_LABELS[WorkInputType.TICK], WorkInputType.TICK.value)
        self.price_spinbox = QSpinBox()
        self.price_spinbox.setRange(0, 1_000_000_000)
        self.price_spinbox.setSingleStep(1000)
        self.price_spinbox.setGroupSeparatorShown(True)

        if work_type is not None:
            self.name_edit.setText(work_type.name)
            index = self.input_type_combo.findData(work_type.input_type.value)
            if index >= 0:
                self.input_type_combo.setCurrentIndex(index)
            self.input_type_combo.setEnabled(False)
            self.price_spinbox.setValue(work_type.unit_price)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        if work_type is not None:
            self.deactivate_button = QPushButton("Ngừng sử dụng")
            self.deactivate_button.clicked.connect(self.deactivate_requested.emit)
            buttons.addButton(self.deactivate_button, QDialogButtonBox.ButtonRole.DestructiveRole)

        layout = QFormLayout(self)
        layout.addRow("Tên công việc", self.name_edit)
        layout.addRow("Loại nhập", self.input_type_combo)
        layout.addRow("Đơn giá", self.price_spinbox)
        layout.addRow(buttons)

    def value(self) -> WorkTypeFormValue:
        return WorkTypeFormValue(
            name=self.name_edit.text(),
            input_type=WorkInputType(str(self.input_type_combo.currentData())),
            unit_price=self.price_spinbox.value(),
        )


class BagTypeDialog(QDialog):
    deactivate_requested = pyqtSignal()

    def __init__(self, parent: QWidget | None = None, *, bag_type: BagType | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Loại bao tổ cắt")
        self.bag_type_id = None if bag_type is None else bag_type.id
        self.name_edit = QLineEdit()
        self.price_spinbox = QSpinBox()
        self.price_spinbox.setRange(0, 1_000_000_000)
        self.price_spinbox.setSingleStep(1000)
        self.price_spinbox.setGroupSeparatorShown(True)

        if bag_type is not None:
            self.name_edit.setText(bag_type.name)
            self.price_spinbox.setValue(bag_type.unit_price)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        if bag_type is not None:
            self.deactivate_button = QPushButton("Ngừng sử dụng")
            self.deactivate_button.clicked.connect(self.deactivate_requested.emit)
            buttons.addButton(self.deactivate_button, QDialogButtonBox.ButtonRole.DestructiveRole)

        layout = QFormLayout(self)
        layout.addRow("Tên loại bao", self.name_edit)
        layout.addRow("Đơn giá", self.price_spinbox)
        layout.addRow(buttons)

    def value(self) -> BagTypeFormValue:
        return BagTypeFormValue(
            name=self.name_edit.text(),
            unit_price=self.price_spinbox.value(),
        )


class AttendancePriceSettingsTab(QWidget):
    attendance_config_changed = pyqtSignal()

    def __init__(self, service: AttendanceSettingsService | None = None) -> None:
        super().__init__()
        self._service = service or AttendanceSettingsService()
        self._work_types: list[WorkType] = []
        self._bag_types: list[BagType] = []

        self.work_type_table = QTableWidget(0, 3)
        self.work_type_table.setHorizontalHeaderLabels(["Tên công việc", "Loại nhập", "Đơn giá"])
        configure_table_widget(self.work_type_table, "attendance.settings.work_types")
        self.work_type_table.itemDoubleClicked.connect(lambda _item: self._edit_work_type())

        self.add_work_type_button = QPushButton("Thêm")
        self.add_work_type_button.clicked.connect(self._add_work_type)

        work_header = QHBoxLayout()
        work_header.addStretch()
        work_header.addWidget(self.add_work_type_button)

        work_group = QGroupBox("Công việc tổ thổi")
        work_layout = QVBoxLayout(work_group)
        work_layout.addLayout(work_header)
        work_layout.addWidget(self.work_type_table)

        self.bag_type_table = QTableWidget(0, 2)
        self.bag_type_table.setHorizontalHeaderLabels(["Tên loại bao", "Đơn giá"])
        configure_table_widget(self.bag_type_table, "attendance.settings.bag_types")
        self.bag_type_table.itemDoubleClicked.connect(lambda _item: self._edit_bag_type())

        self.add_bag_type_button = QPushButton("Thêm")
        self.add_bag_type_button.clicked.connect(self._add_bag_type)

        bag_header = QHBoxLayout()
        bag_header.addStretch()
        bag_header.addWidget(self.add_bag_type_button)

        bag_group = QGroupBox("Loại bao tổ cắt")
        bag_layout = QVBoxLayout(bag_group)
        bag_layout.addLayout(bag_header)
        bag_layout.addWidget(self.bag_type_table)

        layout = QVBoxLayout(self)
        layout.addWidget(work_group, 1)
        layout.addWidget(bag_group, 1)

        self.reload()

    def reload(self) -> None:
        try:
            self._work_types = list(self._service.list_work_types(include_inactive=False))
            self._bag_types = list(self._service.list_bag_types(include_inactive=False))
        except AppError as exc:
            MessageBox.error(self, "Không tải được giá chấm công", str(exc))
            return
        self._render_work_types()
        self._render_bag_types()

    def _render_work_types(self) -> None:
        self.work_type_table.setRowCount(len(self._work_types))
        for row, work_type in enumerate(self._work_types):
            name_item = QTableWidgetItem(work_type.name)
            name_item.setData(Qt.ItemDataRole.UserRole, work_type.id)
            self.work_type_table.setItem(row, 0, name_item)
            self.work_type_table.setItem(row, 1, QTableWidgetItem(INPUT_TYPE_LABELS.get(work_type.input_type, work_type.input_type.value)))
            self.work_type_table.setItem(row, 2, QTableWidgetItem(f"{work_type.unit_price:,}"))

    def _render_bag_types(self) -> None:
        self.bag_type_table.setRowCount(len(self._bag_types))
        for row, bag_type in enumerate(self._bag_types):
            name_item = QTableWidgetItem(bag_type.name)
            name_item.setData(Qt.ItemDataRole.UserRole, bag_type.id)
            self.bag_type_table.setItem(row, 0, name_item)
            self.bag_type_table.setItem(row, 1, QTableWidgetItem(f"{bag_type.unit_price:,}"))

    def _add_work_type(self) -> None:
        dialog = WorkTypeDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = dialog.value()
        try:
            self._service.create_work_type(
                name=value.name,
                input_type=value.input_type,
                unit_price=value.unit_price,
                is_active=True,
            )
        except AppError as exc:
            MessageBox.warning(self, "Không lưu được công việc", str(exc))
            return
        self._notify_changed()

    def _edit_work_type(self) -> None:
        work_type = self._selected_work_type()
        if work_type is None:
            return
        dialog = WorkTypeDialog(self, work_type=work_type)
        dialog.deactivate_requested.connect(lambda: self._deactivate_work_type_from_dialog(dialog, work_type.id))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = dialog.value()
        try:
            self._service.update_work_type(
                work_type.id,
                name=value.name,
                unit_price=value.unit_price,
                is_active=True,
            )
        except AppError as exc:
            MessageBox.warning(self, "Không lưu được công việc", str(exc))
            return
        self._notify_changed()

    def _deactivate_work_type_from_dialog(self, dialog: QDialog, work_type_id: int) -> None:
        if not self._confirm_deactivate(
            self,
            "Ngừng sử dụng công việc",
            "Công việc này sẽ bị ẩn khỏi danh sách và form chấm công mới. Dữ liệu lịch sử vẫn được giữ.",
        ):
            return
        try:
            self._service.set_work_type_active(work_type_id, False)
        except AppError as exc:
            MessageBox.warning(self, "Không đổi được trạng thái", str(exc))
            return
        dialog.accept()
        self._notify_changed()

    def _add_bag_type(self) -> None:
        dialog = BagTypeDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = dialog.value()
        try:
            self._service.create_bag_type(name=value.name, unit_price=value.unit_price, is_active=True)
        except AppError as exc:
            MessageBox.warning(self, "Không lưu được loại bao", str(exc))
            return
        self._notify_changed()

    def _edit_bag_type(self) -> None:
        bag_type = self._selected_bag_type()
        if bag_type is None:
            return
        dialog = BagTypeDialog(self, bag_type=bag_type)
        dialog.deactivate_requested.connect(lambda: self._deactivate_bag_type_from_dialog(dialog, bag_type.id))
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        value = dialog.value()
        try:
            self._service.update_bag_type(
                bag_type.id,
                name=value.name,
                unit_price=value.unit_price,
                is_active=True,
            )
        except AppError as exc:
            MessageBox.warning(self, "Không lưu được loại bao", str(exc))
            return
        self._notify_changed()

    def _deactivate_bag_type_from_dialog(self, dialog: QDialog, bag_type_id: int) -> None:
        if not self._confirm_deactivate(
            self,
            "Ngừng sử dụng loại bao",
            "Loại bao này sẽ bị ẩn khỏi danh sách và form chấm công mới. Dữ liệu lịch sử vẫn được giữ.",
        ):
            return
        try:
            self._service.set_bag_type_active(bag_type_id, False)
        except AppError as exc:
            MessageBox.warning(self, "Không đổi được trạng thái", str(exc))
            return
        dialog.accept()
        self._notify_changed()

    def _notify_changed(self) -> None:
        self.reload()
        self.attendance_config_changed.emit()

    def _selected_work_type(self) -> WorkType | None:
        row = self.work_type_table.currentRow()
        if row < 0 or row >= len(self._work_types):
            return None
        return self._work_types[row]

    def _selected_bag_type(self) -> BagType | None:
        row = self.bag_type_table.currentRow()
        if row < 0 or row >= len(self._bag_types):
            return None
        return self._bag_types[row]

    def _confirm_deactivate(self, parent: QWidget, title: str, message: str) -> bool:
        return (
            QMessageBox.question(
                parent,
                title,
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            == QMessageBox.StandardButton.Yes
        )
