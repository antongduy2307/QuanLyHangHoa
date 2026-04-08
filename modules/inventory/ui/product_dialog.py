from __future__ import annotations

from decimal import Decimal

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
    QVBoxLayout,
)

from core.enums import UnitMode, UnitType
from core.exceptions import ValidationError
from shared.widgets.message_box import MessageBox
from shared.widgets.numeric_inputs import SelectAllSpinBox


class ProductDialog(QDialog):
    def __init__(
        self,
        parent: QDialog | None = None,
        *,
        edit_mode: bool = False,
        product_code_base: str = "",
        product_name: str = "",
        unit_mode: UnitMode = UnitMode.BAO_KG,
        enabled_prices: dict[UnitType, Decimal] | None = None,
        all_prices: dict[UnitType, Decimal] | None = None,
    ) -> None:
        super().__init__(parent)
        self._edit_mode = edit_mode
        self.setWindowTitle("Sửa hàng hóa" if edit_mode else "Tạo hàng hóa")
        self.resize(420, 390)

        self._code_input = QLineEdit(product_code_base)
        self._code_input.setReadOnly(edit_mode)
        self._name_input = QLineEdit(product_name)

        enabled_prices = enabled_prices or {}
        all_prices = all_prices or {}

        self._mode_group = QButtonGroup(self)
        self._bao_kg_radio = QRadioButton("Bao/Kg")
        self._bich_radio = QRadioButton("Bịch")
        self._bao_kg_radio.setChecked(unit_mode == UnitMode.BAO_KG)
        self._bich_radio.setChecked(unit_mode == UnitMode.BICH)
        self._bao_kg_radio.setEnabled(not edit_mode)
        self._bich_radio.setEnabled(not edit_mode)
        self._mode_group.addButton(self._bao_kg_radio)
        self._mode_group.addButton(self._bich_radio)

        self._bao_check = QCheckBox("Bao")
        self._kg_check = QCheckBox("Kg")
        self._bich_check = QCheckBox("Bịch")
        self._bao_check.setChecked(UnitType.BAO in enabled_prices)
        self._kg_check.setChecked(UnitType.KG in enabled_prices)
        self._bich_check.setChecked(UnitType.BICH in enabled_prices or unit_mode == UnitMode.BICH)

        self._price_bao = self._build_price_input(all_prices.get(UnitType.BAO, Decimal("0")))
        self._price_kg = self._build_price_input(all_prices.get(UnitType.KG, Decimal("0")))
        self._price_bich = self._build_price_input(all_prices.get(UnitType.BICH, Decimal("0")))
        self._unit_preview_label = QLabel()
        self._unit_preview_label.setProperty("class", "muted")

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(self._bao_kg_radio)
        mode_layout.addWidget(self._bich_radio)
        mode_layout.addStretch()

        unit_group = QGroupBox("Đơn vị / giá")
        unit_layout = QFormLayout(unit_group)
        unit_layout.addRow(self._bao_check, self._price_bao)
        unit_layout.addRow(self._kg_check, self._price_kg)
        unit_layout.addRow(self._bich_check, self._price_bich)
        unit_layout.addRow("Hiển thị", self._unit_preview_label)

        form_layout = QFormLayout()
        form_layout.addRow("Mã hàng", self._code_input)
        form_layout.addRow("Tên hàng", self._name_input)
        form_layout.addRow("Kiểu đơn vị", mode_layout)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        hint = QLabel("BAO_KG có thể bật BAO, KG hoặc cả hai. BỊCH chỉ cho phép BỊCH.")
        hint.setWordWrap(True)
        hint.setProperty("class", "muted")
        layout.addWidget(hint)
        layout.addLayout(form_layout)
        layout.addWidget(unit_group)
        layout.addStretch()
        layout.addWidget(buttons)

        self._bao_kg_radio.toggled.connect(self._sync_mode_ui)
        self._bich_radio.toggled.connect(self._sync_mode_ui)
        self._bao_check.toggled.connect(self._sync_mode_ui)
        self._kg_check.toggled.connect(self._sync_mode_ui)
        self._sync_mode_ui()

    def payload(self) -> dict[str, object]:
        unit_mode = UnitMode.BAO_KG if self._bao_kg_radio.isChecked() else UnitMode.BICH
        enabled_prices: dict[UnitType, Decimal] = {}
        if unit_mode == UnitMode.BAO_KG:
            if self._bao_check.isChecked():
                enabled_prices[UnitType.BAO] = Decimal(self._price_bao.value())
            if self._kg_check.isChecked():
                enabled_prices[UnitType.KG] = Decimal(self._price_kg.value())
        else:
            enabled_prices[UnitType.BICH] = Decimal(self._price_bich.value())

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
        self._apply_mutual_exclusion(is_bao_kg)
        self._bao_check.setEnabled(is_bao_kg)
        self._kg_check.setEnabled(is_bao_kg)
        self._bich_check.setEnabled(not is_bao_kg)
        self._price_bao.setEnabled(is_bao_kg and self._bao_check.isChecked())
        self._price_kg.setEnabled(is_bao_kg and self._kg_check.isChecked())
        self._price_bich.setEnabled(not is_bao_kg)
        self._unit_preview_label.setText(self._build_unit_preview())

    def _apply_mutual_exclusion(self, is_bao_kg: bool) -> None:
        widgets = (self._bao_check, self._kg_check, self._bich_check)
        for widget in widgets:
            widget.blockSignals(True)
        try:
            if is_bao_kg:
                self._bich_check.setChecked(False)
                if not self._bao_check.isChecked() and not self._kg_check.isChecked():
                    self._bao_check.setChecked(True)
            else:
                self._bao_check.setChecked(False)
                self._kg_check.setChecked(False)
                self._bich_check.setChecked(True)
        finally:
            for widget in widgets:
                widget.blockSignals(False)

    def _build_unit_preview(self) -> str:
        if self._bao_kg_radio.isChecked():
            bao_enabled = self._bao_check.isChecked()
            kg_enabled = self._kg_check.isChecked()
            if bao_enabled and kg_enabled:
                return "Bao + Kg"
            if bao_enabled:
                return "Bao"
            if kg_enabled:
                return "Kg"
            return "Chưa chọn đơn vị"
        return "Bịch"

    def _build_price_input(self, initial_value: Decimal) -> SelectAllSpinBox:
        spin = SelectAllSpinBox()
        spin.setRange(0, 999999999)
        spin.setValue(int(initial_value))
        return spin
