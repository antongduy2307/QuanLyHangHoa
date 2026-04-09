from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QRadioButton, QVBoxLayout, QWidget

from modules.customer.dto import CustomerDTO
from modules.sales.ui.scale import scaled
from shared.formatting.money import format_money


class CustomerPickerWidget(QWidget):
    customer_changed = pyqtSignal()

    def __init__(self, customers: list[CustomerDTO], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._customers = customers
        self._selected_customer: CustomerDTO | None = None
        self._ui_scale = 1.0

        self.walk_in_radio = QRadioButton("Khách lẻ")
        self.customer_radio = QRadioButton("Khách quen")
        self.walk_in_radio.setChecked(True)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm khách theo tên hoặc số điện thoại")
        self.search_input.textChanged.connect(self._update_suggestions)
        self.search_input.installEventFilter(self)

        self._suggestion_popup = QListWidget()
        self._suggestion_popup.setWindowFlags(Qt.WindowType.Popup)
        self._suggestion_popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._suggestion_popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._suggestion_popup.itemClicked.connect(self._select_suggestion)
        self._suggestion_popup.itemActivated.connect(self._select_suggestion)

        self.current_label = QLabel("Khách lẻ")
        self.current_label.setProperty("class", "muted")
        self.balance_label = QLabel("")
        self.balance_label.setProperty("class", "muted")

        customer_row = QHBoxLayout()
        customer_row.addWidget(self.search_input, 1)
        customer_row.addWidget(self.walk_in_radio)
        customer_row.addWidget(self.customer_radio)

        info_layout = QVBoxLayout()
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
        radio_style = f"font-size: {scaled(16, factor)}px; padding: {scaled(4, factor)}px {scaled(8, factor)}px;"
        for radio in (self.walk_in_radio, self.customer_radio):
            radio.setStyleSheet(radio_style)
        self.search_input.setMinimumHeight(scaled(42, factor))
        self.search_input.setMinimumWidth(scaled(420, factor))
        self.search_input.setStyleSheet(f"font-size: {scaled(17, factor)}px; padding: {scaled(8, factor)}px {scaled(12, factor)}px;")
        self._suggestion_popup.setMaximumHeight(scaled(220, factor))
        self._suggestion_popup.setStyleSheet(
            f"QListWidget {{ font-size: {scaled(15, factor)}px; padding: {scaled(4, factor)}px; border: 1px solid #cbd5e1; }}"
            f"QListWidget::item {{ min-height: {scaled(34, factor)}px; padding: {scaled(6, factor)}px {scaled(8, factor)}px; }}"
        )
        self.current_label.setStyleSheet(f"font-size: {scaled(16, factor)}px;")
        self.balance_label.setStyleSheet(f"font-size: {scaled(16, factor)}px;")
        customer_row = self.layout().itemAt(0).layout()
        info_layout = self.layout().itemAt(1).layout()
        if customer_row is not None:
            customer_row.setSpacing(scaled(12, factor))
        if info_layout is not None:
            info_layout.setSpacing(max(2, scaled(2, factor)))
        self.layout().setSpacing(scaled(6, factor))

    def eventFilter(self, watched: object, event: object) -> bool:
        if watched is self.search_input and isinstance(event, QKeyEvent):
            if self._suggestion_popup.isVisible():
                if event.key() == Qt.Key.Key_Down:
                    self._move_selection(1)
                    return True
                if event.key() == Qt.Key.Key_Up:
                    self._move_selection(-1)
                    return True
                if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                    self._activate_current_suggestion()
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self._hide_suggestions()
                    return True
        if watched is self.search_input and isinstance(event, QEvent):
            if event.type() == QEvent.Type.Move or event.type() == QEvent.Type.Resize:
                if self._suggestion_popup.isVisible():
                    self._position_suggestion_popup()
        return super().eventFilter(watched, event)

    def reload_data(self, customers: list[CustomerDTO]) -> None:
        previous_customer_id = None if self._selected_customer is None else self._selected_customer.id
        self._customers = customers
        self._selected_customer = next((customer for customer in customers if customer.id == previous_customer_id), None)
        self._update_suggestions()
        if self._selected_customer is not None and self.customer_radio.isChecked():
            self._set_selected_customer(self._selected_customer)
        elif self.walk_in_radio.isChecked():
            self._sync_mode()

    def selected_customer_id(self) -> int | None:
        return None if self.walk_in_radio.isChecked() or self._selected_customer is None else self._selected_customer.id

    def snapshot_name(self) -> str:
        if self.walk_in_radio.isChecked():
            return "Khách lẻ"
        return self._selected_customer.customer_name if self._selected_customer is not None else ""

    def reset(self) -> None:
        self.walk_in_radio.setChecked(True)
        self.search_input.clear()
        self._selected_customer = None
        self._sync_mode()

    def _sync_mode(self) -> None:
        is_customer = self.customer_radio.isChecked()
        self.search_input.setEnabled(is_customer)
        if not is_customer:
            self.search_input.clear()
            self._hide_suggestions()
        if self.walk_in_radio.isChecked():
            self._selected_customer = None
            self.current_label.setText("Khách lẻ")
            self.balance_label.setText("")
        self.customer_changed.emit()

    def _update_suggestions(self) -> None:
        query = self.search_input.text().strip().lower()
        self._suggestion_popup.clear()
        if not self.customer_radio.isChecked() or not query:
            self._hide_suggestions()
            return
        if query.isdigit():
            matches = [customer for customer in self._customers if customer.phone and query in customer.phone]
        else:
            matches = [customer for customer in self._customers if query in customer.customer_name.lower()]

        if not matches:
            self._hide_suggestions()
            return

        for customer in matches[:20]:
            phone = customer.phone or "-"
            label = f"{customer.customer_name} | {phone} | {format_money(customer.current_balance)}"
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, customer.id)
            self._suggestion_popup.addItem(item)

        self._suggestion_popup.setCurrentRow(0)
        self._position_suggestion_popup()
        self._suggestion_popup.show()
        self._suggestion_popup.raise_()

    def _position_suggestion_popup(self) -> None:
        popup_width = max(self.search_input.width(), scaled(520, self._ui_scale))
        row_count = min(max(self._suggestion_popup.count(), 1), 6)
        row_height = self._suggestion_popup.sizeHintForRow(0)
        if row_height <= 0:
            row_height = scaled(34, self._ui_scale)
        frame = self._suggestion_popup.frameWidth() * 2
        popup_height = row_count * row_height + frame + 4
        global_pos = self.search_input.mapToGlobal(QPoint(0, self.search_input.height()))
        self._suggestion_popup.setGeometry(global_pos.x(), global_pos.y(), popup_width, popup_height)

    def _hide_suggestions(self) -> None:
        self._suggestion_popup.hide()
        self._suggestion_popup.clearSelection()

    def _move_selection(self, delta: int) -> None:
        count = self._suggestion_popup.count()
        if count == 0:
            return
        current_row = self._suggestion_popup.currentRow()
        if current_row < 0:
            current_row = 0
        next_row = max(0, min(count - 1, current_row + delta))
        self._suggestion_popup.setCurrentRow(next_row)

    def _activate_current_suggestion(self) -> None:
        item = self._suggestion_popup.currentItem()
        if item is not None:
            self._select_suggestion(item)

    def _select_suggestion(self, item: QListWidgetItem) -> None:
        customer_id = item.data(Qt.ItemDataRole.UserRole)
        customer = next((customer for customer in self._customers if customer.id == customer_id), None)
        if customer is None:
            return
        self._set_selected_customer(customer)
        self._hide_suggestions()

    def _set_selected_customer(self, customer: CustomerDTO) -> None:
        self._selected_customer = customer
        self.current_label.setText(
            f"Khách: {customer.customer_name}" +
            (f" | SĐT: {customer.phone}" if customer.phone else "")
        )
        balance = customer.current_balance
        color = "#b91c1c" if balance < Decimal("0") else "#14532d"
        self.balance_label.setText(f"Công nợ hiện tại: <span style='color:{color}'>{balance:,.0f}</span>")
        self.customer_changed.emit()
