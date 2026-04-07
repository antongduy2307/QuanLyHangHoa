from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.exceptions import ValidationError
from shared.widgets.message_box import MessageBox


class AdjustmentRowWidget(QWidget):
    def __init__(self, product_options: list[tuple[int, str]], on_remove: callable) -> None:
        super().__init__()
        self._remove_callback = on_remove
        self.product_combo = QComboBox()
        for product_id, label in product_options:
            self.product_combo.addItem(label, product_id)

        self.quantity_input = QDoubleSpinBox()
        self.quantity_input.setDecimals(3)
        self.quantity_input.setRange(0, 999999999)
        self.quantity_input.setAlignment(Qt.AlignmentFlag.AlignRight)

        remove_button = QPushButton("Xóa dòng")
        remove_button.clicked.connect(lambda: self._remove_callback(self))

        layout = QHBoxLayout(self)
        layout.addWidget(self.product_combo, 3)
        layout.addWidget(self.quantity_input, 1)
        layout.addWidget(remove_button)


class InventoryAdjustmentDialog(QDialog):
    def __init__(self, product_options: list[tuple[int, str]], parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Điều chỉnh kho")
        self.resize(640, 360)
        self._product_options = product_options
        self._rows: list[AdjustmentRowWidget] = []

        self._rows_container = QWidget()
        self._rows_layout = QVBoxLayout(self._rows_container)
        self._rows_layout.setContentsMargins(0, 0, 0, 0)
        self._rows_layout.setSpacing(8)
        self._rows_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._rows_container)

        add_button = QPushButton("Thêm dòng")
        add_button.clicked.connect(self._add_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        hint = QLabel("Nhập tồn mới theo đơn vị chuẩn: BAO cho BAO_KG, BỊCH cho BỊCH")
        hint.setProperty("class", "muted")
        layout.addWidget(hint)
        layout.addWidget(scroll)
        layout.addWidget(add_button)
        layout.addWidget(buttons)

        self._add_row()

    def payload(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for row in self._rows:
            items.append(
                {
                    "product_id": row.product_combo.currentData(),
                    "new_quantity": Decimal(str(row.quantity_input.value())),
                }
            )
        return items

    def _add_row(self) -> None:
        row = AdjustmentRowWidget(self._product_options, self._remove_row)
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
                if Decimal(str(item["new_quantity"])) < Decimal("0"):
                    raise ValidationError("Tồn mới phải >= 0.")
        except Exception as exc:
            MessageBox.error(self, "Lỗi dữ liệu", str(exc))
            return
        self.accept()
