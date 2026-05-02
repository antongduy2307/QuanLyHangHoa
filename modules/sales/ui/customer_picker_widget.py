from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QRadioButton, QVBoxLayout, QWidget

from modules.customer.dto import CustomerDTO
from modules.sales.ui.scale import scaled, scaled_font
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit


class CustomerPickerWidget(QWidget):
    customer_changed = pyqtSignal()

    def __init__(
        self,
        customers: list[CustomerDTO],
        parent: QWidget | None = None,
        *,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self._customers = customers
        self._selected_customer: CustomerDTO | None = None
        self._ui_scale = 1.0
        self._compact = compact
        self._locked = False

        self.walk_in_radio = QRadioButton("Khách lẻ")
        self.customer_radio = QRadioButton("Khách quen")
        self.walk_in_radio.setChecked(True)

        self.search_input = AutocompleteLineEdit()
        self.search_input.setPlaceholderText("Tìm theo tên khách hàng")
        self.search_input.textEdited.connect(self._handle_search_text_edited)
        self.search_input.suggestion_selected.connect(self._handle_suggestion_selected)
        self.search_input.returnPressed.connect(self._select_best_match)

        self.clear_button = QPushButton("×")
        self.clear_button.setObjectName("salesCustomerClearButton")
        self.clear_button.setVisible(False)
        self.clear_button.clicked.connect(self._clear_customer)

        self.current_label = QLabel("Khách lẻ")
        self.current_label.setProperty("class", "muted")
        self.balance_label = QLabel("")
        self.balance_label.setProperty("class", "muted")

        customer_row = QHBoxLayout()
        customer_row.setContentsMargins(0, 0, 0, 0)
        customer_row.addWidget(self.search_input, 1)
        customer_row.addWidget(self.clear_button)
        if not compact:
            customer_row.addWidget(self.walk_in_radio)
            customer_row.addWidget(self.customer_radio)

        info_layout = QVBoxLayout()
        info_layout.setContentsMargins(0, 0, 0, 0)
        if not compact:
            info_layout.addWidget(self.current_label)
        info_layout.addWidget(self.balance_label)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(customer_row)
        layout.addLayout(info_layout)

        self.walk_in_radio.toggled.connect(self._sync_mode)
        self.customer_radio.toggled.connect(self._sync_mode)
        self.apply_ui_scale(1.0)
        self._sync_mode()

    def apply_ui_scale(self, factor: float) -> None:
        self._ui_scale = factor
        radio_style = f"font-size: {scaled_font(16, factor)}px; padding: {scaled(4, factor)}px {scaled(8, factor)}px;"
        for radio in (self.walk_in_radio, self.customer_radio):
            radio.setStyleSheet(radio_style)
        self.search_input.setMinimumHeight(scaled(42, factor))
        self.search_input.setMinimumWidth(scaled(320 if self._compact else 420, factor))
        self.search_input.setStyleSheet(
            f"font-size: {scaled_font(17, factor)}px; padding: {scaled(8, factor)}px {scaled(12, factor)}px;"
        )
        self.clear_button.setMinimumHeight(scaled(42, factor))
        self.clear_button.setMaximumWidth(scaled(42, factor))
        self.search_input.set_popup_minimum_width(scaled(460 if self._compact else 520, factor))
        self.search_input.set_popup_maximum_height(scaled(220, factor))
        self.search_input.set_popup_stylesheet(
            f"QListWidget {{ font-size: {scaled_font(15, factor)}px; padding: {scaled(4, factor)}px; border: 1px solid #cbd5e1; }}"
            f"QListWidget::item {{ min-height: {scaled(34, factor)}px; padding: {scaled(6, factor)}px {scaled(8, factor)}px; }}"
        )
        self.current_label.setStyleSheet(f"font-size: {scaled_font(16, factor)}px;")
        self.balance_label.setStyleSheet(f"font-size: {scaled_font(15 if self._compact else 16, factor)}px;")

        customer_row = self.layout().itemAt(0).layout()
        info_layout = self.layout().itemAt(1).layout()
        if customer_row is not None:
            customer_row.setSpacing(scaled(8 if self._compact else 12, factor))
        if info_layout is not None:
            info_layout.setSpacing(max(2, scaled(2, factor)))
        self.layout().setSpacing(scaled(4 if self._compact else 6, factor))

    def reload_data(self, customers: list[CustomerDTO]) -> None:
        previous_customer_id = None if self._selected_customer is None else self._selected_customer.id
        self._customers = customers
        self._selected_customer = next((customer for customer in customers if customer.id == previous_customer_id), None)
        if self._selected_customer is not None:
            self.search_input.blockSignals(True)
            self.search_input.setText(self._search_text_for_customer(self._selected_customer))
            self.search_input.blockSignals(False)
        elif not self._compact and self.walk_in_radio.isChecked():
            self.search_input.clear()
        self._update_suggestions()
        self._refresh_customer_state()
        if self._compact or self.walk_in_radio.isChecked():
            self.customer_changed.emit()

    def selected_customer_id(self) -> int | None:
        if self._compact:
            return None if self._selected_customer is None else self._selected_customer.id
        return None if self.walk_in_radio.isChecked() or self._selected_customer is None else self._selected_customer.id

    def snapshot_name(self) -> str:
        if self.selected_customer_id() is None:
            return "Khách lẻ"
        return self._selected_customer.customer_name if self._selected_customer is not None else ""

    def reset(self) -> None:
        if self._locked:
            return
        self.search_input.clear()
        self.search_input.hide_suggestions()
        self._selected_customer = None
        if not self._compact:
            self.walk_in_radio.setChecked(True)
        self._sync_mode()

    def lock_customer(self, customer: CustomerDTO | None) -> None:
        self._locked = True
        self._selected_customer = customer
        if self._compact:
            if customer is None:
                self.search_input.setText("Khách lẻ")
            else:
                self.search_input.setText(self._search_text_for_customer(customer))
        else:
            self.walk_in_radio.setChecked(customer is None)
            self.customer_radio.setChecked(customer is not None)
            if customer is None:
                self.search_input.clear()
            else:
                self.search_input.setText(self._search_text_for_customer(customer))
        self.search_input.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.clear_button.setVisible(False)
        self.walk_in_radio.setEnabled(False)
        self.customer_radio.setEnabled(False)
        self._refresh_customer_state()

    def unlock_customer(self) -> None:
        self._locked = False
        self.search_input.setEnabled(True)
        self.walk_in_radio.setEnabled(True)
        self.customer_radio.setEnabled(True)
        self._sync_mode()

    def _sync_mode(self) -> None:
        if self._locked:
            self._refresh_customer_state()
            self.customer_changed.emit()
            return
        if self._compact:
            self.search_input.setEnabled(True)
            self._refresh_customer_state()
            self.customer_changed.emit()
            return

        is_customer = self.customer_radio.isChecked()
        self.search_input.setEnabled(is_customer)
        if not is_customer:
            self.search_input.clear()
            self.search_input.hide_suggestions()
            self._selected_customer = None
        self._refresh_customer_state()
        self.customer_changed.emit()

    def _handle_search_text_edited(self, text: str) -> None:
        if self._locked:
            return
        previous_customer_id = self.selected_customer_id()
        if self._selected_customer is not None and text.strip() != self._search_text_for_customer(self._selected_customer):
            self._selected_customer = None
        self._update_suggestions(text)
        self._refresh_customer_state()
        if previous_customer_id != self.selected_customer_id():
            self.customer_changed.emit()

    def _update_suggestions(self, text: str | None = None) -> None:
        query = (self.search_input.text() if text is None else text).strip().lower()
        if (not self._compact and not self.customer_radio.isChecked()) or not query:
            self.search_input.hide_suggestions()
            return

        matches = [customer for customer in self._customers if query in customer.customer_name.lower()]
        suggestions = [(customer.customer_name, customer.id) for customer in matches[:20]]
        self.search_input.set_suggestions(suggestions)

    def _handle_suggestion_selected(self, customer_id: object) -> None:
        if self._locked:
            return
        if customer_id is None:
            return
        customer = next((customer for customer in self._customers if customer.id == int(customer_id)), None)
        if customer is None:
            return
        self._selected_customer = customer
        self.search_input.setText(self._search_text_for_customer(customer))
        self.search_input.hide_suggestions()
        self._refresh_customer_state()
        self.customer_changed.emit()

    def _select_best_match(self) -> None:
        if self._locked:
            return
        query = self.search_input.text().strip().lower()
        if not query or (not self._compact and not self.customer_radio.isChecked()):
            return
        customer = next((candidate for candidate in self._customers if query in candidate.customer_name.lower()), None)
        if customer is None:
            return
        self._selected_customer = customer
        self.search_input.setText(self._search_text_for_customer(customer))
        self.search_input.hide_suggestions()
        self._refresh_customer_state()
        self.customer_changed.emit()

    def _clear_customer(self) -> None:
        if self._locked:
            return
        self.search_input.clear()
        self.search_input.hide_suggestions()
        self._selected_customer = None
        if not self._compact:
            self.walk_in_radio.setChecked(True)
        self._refresh_customer_state()
        self.customer_changed.emit()

    def _refresh_customer_state(self) -> None:
        if self.selected_customer_id() is None:
            if not self._compact and self.walk_in_radio.isChecked():
                self.current_label.setText("Khách lẻ")
                self.balance_label.setText("")
            elif self.search_input.text().strip():
                if not self._compact:
                    self.current_label.setText("Chưa chọn khách từ danh sách gợi ý")
                self.balance_label.setText("")
            else:
                if not self._compact:
                    self.current_label.setText("Khách lẻ")
                self.balance_label.setText("")
            self.clear_button.setVisible(False)
            return

        customer = self._selected_customer
        if customer is None:
            self.clear_button.setVisible(False)
            self.balance_label.setText("")
            return

        if not self._compact:
            self.current_label.setText(
                f"Khách: {customer.customer_name}"
                + (f" | SĐT: {customer.phone}" if customer.phone else "")
            )

        balance = customer.current_balance
        if balance >= Decimal("0"):
            self.balance_label.setText(f"Công nợ hiện tại: {balance:,.0f}")
        else:
            self.balance_label.setText(f"Shop đang nợ khách: {abs(balance):,.0f}")
        self.clear_button.setVisible(True)

    @staticmethod
    def _search_text_for_customer(customer: CustomerDTO) -> str:
        return customer.customer_name
