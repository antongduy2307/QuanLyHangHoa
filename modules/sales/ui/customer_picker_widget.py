from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QListWidget, QRadioButton, QVBoxLayout, QWidget

from modules.customer.dto import CustomerDTO


class CustomerPickerWidget(QWidget):
    customer_changed = pyqtSignal()

    def __init__(self, customers: list[CustomerDTO], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._customers = customers
        self._selected_customer: CustomerDTO | None = None

        self.walk_in_radio = QRadioButton("Khach le")
        self.customer_radio = QRadioButton("Khach quen")
        self.walk_in_radio.setChecked(True)

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tim khach theo ten hoac so dien thoai")
        self.search_input.textChanged.connect(self._update_suggestions)

        self.suggestion_list = QListWidget()
        self.suggestion_list.itemClicked.connect(self._select_suggestion)
        self.suggestion_list.setMaximumHeight(120)

        self.current_label = QLabel("Khach le")
        self.current_label.setProperty("class", "muted")
        self.balance_label = QLabel("")
        self.balance_label.setProperty("class", "muted")

        toggle_layout = QHBoxLayout()
        toggle_layout.addWidget(self.walk_in_radio)
        toggle_layout.addWidget(self.customer_radio)
        toggle_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(toggle_layout)
        layout.addWidget(self.search_input)
        layout.addWidget(self.suggestion_list)
        layout.addWidget(self.current_label)
        layout.addWidget(self.balance_label)

        self.walk_in_radio.toggled.connect(self._sync_mode)
        self.customer_radio.toggled.connect(self._sync_mode)
        self._sync_mode()

    def selected_customer_id(self) -> int | None:
        return None if self.walk_in_radio.isChecked() or self._selected_customer is None else self._selected_customer.id

    def snapshot_name(self) -> str:
        if self.walk_in_radio.isChecked():
            return "Khach le"
        return self._selected_customer.customer_name if self._selected_customer is not None else ""

    def reset(self) -> None:
        self.walk_in_radio.setChecked(True)
        self.search_input.clear()
        self._selected_customer = None
        self._sync_mode()

    def _sync_mode(self) -> None:
        is_customer = self.customer_radio.isChecked()
        self.search_input.setVisible(is_customer)
        self.suggestion_list.setVisible(is_customer)
        if self.walk_in_radio.isChecked():
            self._selected_customer = None
            self.current_label.setText("Khach le")
            self.balance_label.setText("")
        self.customer_changed.emit()

    def _update_suggestions(self) -> None:
        query = self.search_input.text().strip().lower()
        self.suggestion_list.clear()
        if not query:
            return
        if query.isdigit():
            matches = [customer for customer in self._customers if customer.phone and query in customer.phone]
        else:
            matches = [customer for customer in self._customers if query in customer.customer_name.lower()]
        for customer in matches[:20]:
            label = customer.customer_name if not customer.phone else f"{customer.customer_name} - {customer.phone}"
            self.suggestion_list.addItem(label)
            self.suggestion_list.item(self.suggestion_list.count() - 1).setData(256, customer.id)

    def _select_suggestion(self, *_args: object) -> None:
        item = self.suggestion_list.currentItem()
        if item is None:
            return
        customer_id = item.data(256)
        self._selected_customer = next((customer for customer in self._customers if customer.id == customer_id), None)
        if self._selected_customer is None:
            return
        self.current_label.setText(
            f"Khach: {self._selected_customer.customer_name}" +
            (f" | SDT: {self._selected_customer.phone}" if self._selected_customer.phone else "")
        )
        balance = self._selected_customer.current_balance
        color = "#b91c1c" if balance < Decimal("0") else "#14532d"
        self.balance_label.setText(f"Cong no hien tai: <span style='color:{color}'>{balance:,.0f}</span>")
        self.customer_changed.emit()

