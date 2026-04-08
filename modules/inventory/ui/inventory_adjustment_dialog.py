from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.db import SessionFactory
from core.exceptions import ValidationError
from modules.inventory.controller import InventoryController
from shared.widgets.message_box import MessageBox
from shared.widgets.numeric_inputs import SelectAllSpinBox


class AdjustmentRowWidget(QWidget):
    def __init__(self, product_options: list[tuple[int, str]], controller: InventoryController, on_remove: callable) -> None:
        super().__init__()
        self._controller = controller
        self._remove_callback = on_remove
        self._suspend_sync = False

        self.product_combo = QComboBox()
        for product_id, label in product_options:
            self.product_combo.addItem(label, product_id)

        self.current_quantity_label = QLabel("0")
        self.current_quantity_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.new_quantity_input = SelectAllSpinBox()
        self.new_quantity_input.setRange(0, 999999999)

        remove_button = QPushButton("Xóa dòng")
        remove_button.clicked.connect(lambda: self._remove_callback(self))

        layout = QHBoxLayout(self)
        layout.addWidget(self.product_combo, 3)
        layout.addWidget(self.current_quantity_label, 1)
        layout.addWidget(self.new_quantity_input, 1)
        layout.addWidget(remove_button)

        self.product_combo.currentIndexChanged.connect(self.refresh_current_quantity)
        self.refresh_current_quantity()

    def payload(self) -> dict[str, object]:
        return {
            "product_id": self.product_combo.currentData(),
            "new_quantity": Decimal(self.new_quantity_input.value()),
        }

    def refresh_current_quantity(self) -> None:
        if self._suspend_sync:
            return
        product_id = self.product_combo.currentData()
        if product_id is None:
            self.current_quantity_label.setText("0")
            self.new_quantity_input.setValue(0)
            return
        current_quantity = self._controller.get_current_quantity(int(product_id))
        self.current_quantity_label.setText(self._format_quantity(current_quantity))
        self._suspend_sync = True
        try:
            self.new_quantity_input.setValue(int(current_quantity))
        finally:
            self._suspend_sync = False

    def _format_quantity(self, value: Decimal) -> str:
        normalized = value.quantize(Decimal("0.001")).normalize()
        return format(normalized, "f").rstrip("0").rstrip(".") or "0"


class InventoryAdjustmentDialog(QDialog):
    def __init__(self, product_options: list[tuple[int, str]], parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Điều chỉnh kho")
        self.resize(780, 360)
        self._product_options = product_options
        self._controller = InventoryController(SessionFactory)
        self._rows: list[AdjustmentRowWidget] = []

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        self._rows_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._rows_container)

        header = QGridLayout()
        header.addWidget(QLabel("Hàng hóa"), 0, 0)
        header.addWidget(QLabel("Tồn hiện tại"), 0, 1)
        header.addWidget(QLabel("Tồn mới"), 0, 2)

        add_button = QPushButton("Thêm dòng")
        add_button.clicked.connect(self._add_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        hint = QLabel("Điều chỉnh kho dùng tồn hiện tại thật làm old quantity và tồn mới nhập vào làm new quantity.")
        hint.setProperty("class", "muted")
        layout.addWidget(hint)
        layout.addLayout(header)
        layout.addWidget(scroll)
        layout.addWidget(add_button)
        layout.addWidget(buttons)

        self._add_row()

    def payload(self) -> list[dict[str, object]]:
        return [row.payload() for row in self._rows]

    def _add_row(self) -> None:
        row = AdjustmentRowWidget(self._product_options, self._controller, self._remove_row)
        self._rows.append(row)
        self._rows_layout.insertWidget(self._rows_layout.count() - 1, row)

    def _remove_row(self, row: AdjustmentRowWidget) -> None:
        if len(self._rows) == 1:
            return
        self._rows.remove(row)
        row.setParent(None)
        row.deleteLater()

    def _handle_accept(self) -> None:
        try:
            items = self.payload()
            if not items:
                raise ValidationError("Phải có ít nhất 1 dòng điều chỉnh.")
            for item in items:
                if item["product_id"] is None:
                    raise ValidationError("Phải chọn hàng hóa.")
                if Decimal(item["new_quantity"]) < Decimal("0"):
                    raise ValidationError("Tồn mới phải >= 0.")
        except Exception as exc:
            MessageBox.error(self, "Lỗi dữ liệu", str(exc))
            return
        self.accept()
