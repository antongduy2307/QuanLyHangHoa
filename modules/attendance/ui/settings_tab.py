from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.exceptions import AppError
from modules.attendance.models import BagType, WorkInputType, WorkType
from modules.attendance.product_sync_service import AttendanceProductSyncService
from modules.attendance.settings_service import AttendanceSettingsService
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


logger = logging.getLogger(__name__)
INCOMPLETE_ROW_BACKGROUND = QColor(255, 235, 235)

INPUT_TYPE_LABELS = {
    WorkInputType.QUANTITY: "Số lượng",
    WorkInputType.TICK: "Tick",
}


def _format_decimal(value: object) -> str:
    text = str(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


@dataclass(frozen=True, slots=True)
class WorkTypeFormValue:
    name: str
    input_type: WorkInputType
    unit_price: int


@dataclass(frozen=True, slots=True)
class BagTypeFormValue:
    name: str
    quota_quantity: Decimal | int | str
    excess_unit_price: int
    is_excluded_from_attendance: bool = False


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
        self.quota_input = QLineEdit("0")
        self.quota_input.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.quota_input.setPlaceholderText("0, 0.5, 1, 1.5...")
        self.excess_price_spinbox = QSpinBox()
        self.excess_price_spinbox.setRange(0, 1_000_000_000)
        self.excess_price_spinbox.setSingleStep(1000)
        self.excess_price_spinbox.setGroupSeparatorShown(True)
        self.exclude_checkbox = QCheckBox("Không dùng cho chấm công")

        if bag_type is not None:
            self.name_edit.setText(bag_type.name)
            if bag_type.is_product_linked:
                self.name_edit.setReadOnly(True)
                self.name_edit.setToolTip("Tên này được đồng bộ từ danh mục hàng hóa.")
            self.quota_input.setText(_format_decimal(bag_type.quota_quantity))
            self.excess_price_spinbox.setValue(int(bag_type.excess_unit_price))
            self.exclude_checkbox.setChecked(bool(bag_type.is_excluded_from_attendance))

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        if bag_type is not None:
            self.deactivate_button = QPushButton("Ngừng sử dụng")
            self.deactivate_button.clicked.connect(self.deactivate_requested.emit)
            buttons.addButton(self.deactivate_button, QDialogButtonBox.ButtonRole.DestructiveRole)

        layout = QFormLayout(self)
        layout.addRow("Tên loại bao", self.name_edit)
        layout.addRow("Số lượng khoán", self.quota_input)
        layout.addRow("Thưởng mỗi bao vượt khoán", self.excess_price_spinbox)
        layout.addRow(self.exclude_checkbox)
        layout.addRow(buttons)

    def value(self) -> BagTypeFormValue:
        return BagTypeFormValue(
            name=self.name_edit.text(),
            quota_quantity=self.quota_input.text().strip() or "0",
            excess_unit_price=self.excess_price_spinbox.value(),
            is_excluded_from_attendance=self.exclude_checkbox.isChecked(),
        )


class AttendancePriceSettingsTab(QWidget):
    attendance_config_changed = pyqtSignal()

    def __init__(
        self,
        service: AttendanceSettingsService | None = None,
        *,
        product_sync_service: AttendanceProductSyncService | None = None,
    ) -> None:
        super().__init__()
        self._service = service or AttendanceSettingsService()
        self._product_sync_service = product_sync_service or AttendanceProductSyncService()
        self._work_types: list[WorkType] = []
        self._bag_types: list[BagType] = []
        self._rendering_bag_types = False

        self.work_type_table = QTableWidget(0, 3)
        self.work_type_table.setHorizontalHeaderLabels(["Tên công việc", "Loại nhập", "Đơn giá"])
        configure_table_widget(self.work_type_table, "attendance.settings.work_types")
        self.work_type_table.itemDoubleClicked.connect(lambda _item: self._edit_work_type())

        self.add_work_type_button = QPushButton("Thêm")
        self.add_work_type_button.clicked.connect(self._add_work_type)

        work_header = QHBoxLayout()
        work_header.addStretch()
        work_header.addWidget(self.add_work_type_button)

        self.work_group = QGroupBox("Công việc tổ thổi")
        work_layout = QVBoxLayout(self.work_group)
        work_layout.addLayout(work_header)
        work_layout.addWidget(self.work_type_table)

        self.sync_warning_label = QLabel()
        self.sync_warning_label.setWordWrap(True)
        self.sync_warning_label.setStyleSheet(
            "QLabel { background: #fff4ce; border: 1px solid #e0b400; border-radius: 4px; padding: 6px; }"
        )
        self.sync_warning_label.hide()

        self.bag_type_table = QTableWidget(0, 4)
        self.bag_type_table.setHorizontalHeaderLabels(
            ["Tên loại bao", "Số lượng khoán", "Thưởng mỗi bao vượt khoán", "Không dùng cho chấm công"]
        )
        configure_table_widget(self.bag_type_table, "attendance.settings.bag_types")
        self.bag_type_table.itemDoubleClicked.connect(lambda _item: self._edit_bag_type())

        self.bag_group = QGroupBox("Loại bao tổ cắt")
        bag_layout = QVBoxLayout(self.bag_group)
        bag_layout.addWidget(self.sync_warning_label)
        bag_layout.addWidget(self.bag_type_table)

        self.section_combo = QComboBox()
        self.section_combo.addItem("Công việc tổ thổi")
        self.section_combo.addItem("Loại bao tổ cắt")
        self.section_stack = QStackedWidget()
        self.section_stack.addWidget(self.work_group)
        self.section_stack.addWidget(self.bag_group)
        self.section_combo.currentIndexChanged.connect(self.section_stack.setCurrentIndex)

        selector_layout = QHBoxLayout()
        selector_layout.addWidget(QLabel("Nhóm cài đặt"))
        selector_layout.addWidget(self.section_combo)
        selector_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(selector_layout)
        layout.addWidget(self.section_stack, 1)

        self.reload()

    def reload(self) -> None:
        sync_warnings: list[str] = []
        try:
            sync_result = self._product_sync_service.sync_products_to_cut_work()
            sync_warnings = list(sync_result.warnings)
        except Exception as exc:
            logger.warning("Could not sync products into attendance CUT work settings: %s", exc)
        for warning in sync_warnings:
            logger.warning("Attendance product sync warning: %s", warning)
        self._set_sync_warnings(sync_warnings)

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
        self._rendering_bag_types = True
        self.bag_type_table.setRowCount(len(self._bag_types))
        for row, bag_type in enumerate(self._bag_types):
            name_item = QTableWidgetItem(bag_type.name)
            name_item.setData(Qt.ItemDataRole.UserRole, bag_type.id)
            if bag_type.is_product_linked:
                name_item.setFlags(name_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                name_item.setToolTip("Tên được đồng bộ từ danh mục hàng hóa.")
            if bag_type.is_legacy:
                name_item.setText(f"{bag_type.name} (Dữ liệu cũ)")
            quota_item = QTableWidgetItem(self._format_decimal(bag_type.quota_quantity))
            price_item = QTableWidgetItem(f"{int(bag_type.excess_unit_price):,}")
            self.bag_type_table.setItem(row, 0, name_item)
            self.bag_type_table.setItem(row, 1, quota_item)
            self.bag_type_table.setItem(row, 2, price_item)
            checkbox_holder = self._build_exclusion_checkbox_cell(bag_type)
            self.bag_type_table.setCellWidget(row, 3, checkbox_holder)
            if self._is_incomplete_product_linked_bag_type(bag_type):
                for item in (name_item, quota_item, price_item):
                    item.setBackground(INCOMPLETE_ROW_BACKGROUND)
                checkbox_holder.setStyleSheet("background: rgb(255, 235, 235);")
            else:
                checkbox_holder.setStyleSheet("")
        self._rendering_bag_types = False

    def _build_exclusion_checkbox_cell(self, bag_type: BagType) -> QWidget:
        checkbox = QCheckBox()
        checkbox.setChecked(bool(bag_type.is_excluded_from_attendance))
        checkbox.setToolTip("Tick nếu mặt hàng này không dùng cho chấm công.")
        checkbox.stateChanged.connect(lambda _state, bag_type_id=bag_type.id: self._toggle_bag_type_exclusion(bag_type_id))
        holder = QWidget()
        layout = QHBoxLayout(holder)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(checkbox)
        return holder

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
            self._service.create_bag_type(
                name=value.name,
                quota_quantity=value.quota_quantity,
                excess_unit_price=value.excess_unit_price,
                is_active=True,
                is_excluded_from_attendance=value.is_excluded_from_attendance,
            )
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
                quota_quantity=value.quota_quantity,
                excess_unit_price=value.excess_unit_price,
                is_active=True,
                is_excluded_from_attendance=value.is_excluded_from_attendance,
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

    def _toggle_bag_type_exclusion(self, bag_type_id: int) -> None:
        if self._rendering_bag_types:
            return
        bag_type = next((item for item in self._bag_types if item.id == bag_type_id), None)
        if bag_type is None:
            return
        try:
            self._service.update_bag_type(
                bag_type.id,
                name=bag_type.name,
                quota_quantity=bag_type.quota_quantity,
                excess_unit_price=bag_type.excess_unit_price,
                is_active=bag_type.is_active,
                is_excluded_from_attendance=not bool(bag_type.is_excluded_from_attendance),
            )
        except AppError as exc:
            MessageBox.warning(self, "Không lưu được trạng thái chấm công", str(exc))
            return
        self._notify_changed()

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

    def _format_decimal(self, value: object) -> str:
        text = str(value)
        if "." in text:
            text = text.rstrip("0").rstrip(".")
        return text

    def _is_incomplete_product_linked_bag_type(self, bag_type: BagType) -> bool:
        return (
            bool(bag_type.is_product_linked)
            and bool(bag_type.is_active)
            and not bool(bag_type.is_excluded_from_attendance)
            and (bag_type.quota_quantity == 0 or bag_type.excess_unit_price == 0)
        )

    def _set_sync_warnings(self, warnings: list[str]) -> None:
        if not warnings:
            self.sync_warning_label.hide()
            self.sync_warning_label.setText("")
            return
        self.sync_warning_label.setText("Có một số hàng hóa chưa đồng bộ được. Vui lòng kiểm tra tên hàng bị trùng.")
        self.sync_warning_label.show()

    def focus_first_incomplete_cut_work(self, first_incomplete_id: int | None = None) -> None:
        self.reload()
        self.section_combo.setCurrentIndex(1)
        target_row = -1
        for row, bag_type in enumerate(self._bag_types):
            if first_incomplete_id is not None and bag_type.id == first_incomplete_id:
                target_row = row
                break
            if first_incomplete_id is None and self._is_incomplete_product_linked_bag_type(bag_type):
                target_row = row
                break
        if target_row < 0:
            return
        self.bag_type_table.selectRow(target_row)
        item = self.bag_type_table.item(target_row, 0)
        if item is not None:
            self.bag_type_table.scrollToItem(item)
        self.bag_type_table.setFocus()
