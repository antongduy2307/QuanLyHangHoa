from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QDoubleSpinBox,
    QVBoxLayout,
)

from core.enums import UnitMode, UnitType
from core.exceptions import ValidationError
from shared.widgets.message_box import MessageBox


class ProductDialog(QDialog):
    def __init__(self, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Tạo hàng hóa")
        self.resize(420, 360)

        self._code_input = QLineEdit()
        self._name_input = QLineEdit()

        self._mode_group = QButtonGroup(self)
        self._bao_kg_radio = QRadioButton("Bao/Kg")
        self._bich_radio = QRadioButton("Bịch")
        self._bao_kg_radio.setChecked(True)
        self._mode_group.addButton(self._bao_kg_radio)
        self._mode_group.addButton(self._bich_radio)

        self._bao_check = QCheckBox("Bao")
        self._kg_check = QCheckBox("Kg")
        self._bich_check = QCheckBox("Bịch")
        self._bao_check.setChecked(True)
        self._kg_check.setChecked(True)
        self._bich_check.setChecked(True)

        self._price_bao = self._build_price_input()
        self._price_kg = self._build_price_input()
        self._price_bich = self._build_price_input()

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self._bao_kg_radio)
        mode_layout.addWidget(self._bich_radio)
        mode_layout.addStretch()

        unit_group = QGroupBox("Đơn vị / giá")
        unit_layout = QFormLayout(unit_group)
        unit_layout.addRow(self._bao_check, self._price_bao)
        unit_layout.addRow(self._kg_check, self._price_kg)
        unit_layout.addRow(self._bich_check, self._price_bich)

        form_layout = QFormLayout()
        form_layout.addRow("Mã hàng", self._code_input)
        form_layout.addRow("Tên hàng", self._name_input)
        form_layout.addRow("Kiểu đơn vị", mode_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        hint = QLabel("BAO_KG có thể bật BAO, KG hoặc cả hai. BỊCH chỉ cho phép BỊCH.")
        hint.setWordWrap(True)
        hint.setProperty("class", "muted")
        layout.addWidget(hint)
        layout.addLayout(form_layout)
        layout.addWidget(unit_group)
        layout.addStretch()
        layout.addWidget(buttons)

        self._bao_kg_radio.toggled.connect(self._sync_mode_ui)
        self._sync_mode_ui()

    def payload(self) -> dict[str, object]:
        unit_mode = UnitMode.BAO_KG if self._bao_kg_radio.isChecked() else UnitMode.BICH
        enabled_prices: dict[UnitType, Decimal] = {}
        if unit_mode == UnitMode.BAO_KG:
            if self._bao_check.isChecked():
                enabled_prices[UnitType.BAO] = Decimal(str(self._price_bao.value()))
            if self._kg_check.isChecked():
                enabled_prices[UnitType.KG] = Decimal(str(self._price_kg.value()))
        else:
            enabled_prices[UnitType.BICH] = Decimal(str(self._price_bich.value()))

        return {
            "product_code_base": self._code_input.text(),
            "product_name": self._name_input.text(),
            "unit_mode": unit_mode,
            "enabled_prices": enabled_prices,
        }

    def _handle_accept(self) -> None:
        try:
            payload = self.payload()
            if not str(payload["product_code_base"]).strip():
                raise ValidationError("Mã hàng không được để trống.")
            if not str(payload["product_name"]).strip():
                raise ValidationError("Tên hàng không được để trống.")
            if not payload["enabled_prices"]:
                raise ValidationError("Phải chọn ít nhất 1 đơn vị được enable.")
            for price in payload["enabled_prices"].values():
                if price <= Decimal("0"):
                    raise ValidationError("Giá phải > 0.")
        except Exception as exc:
            MessageBox.error(self, "Lỗi dữ liệu", str(exc))
            return
        self.accept()

    def _sync_mode_ui(self) -> None:
        is_bao_kg = self._bao_kg_radio.isChecked()
        self._bao_check.setEnabled(is_bao_kg)
        self._kg_check.setEnabled(is_bao_kg)
        self._price_bao.setEnabled(is_bao_kg and self._bao_check.isChecked())
        self._price_kg.setEnabled(is_bao_kg and self._kg_check.isChecked())
        self._bich_check.setChecked(not is_bao_kg)
        self._bich_check.setEnabled(not is_bao_kg)
        self._price_bich.setEnabled(not is_bao_kg)

    def _build_price_input(self) -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setDecimals(2)
        spin.setRange(0, 999999999)
        spin.setAlignment(Qt.AlignmentFlag.AlignRight)
        return spin

