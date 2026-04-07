from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from modules.customer.controller import CustomerController
from modules.customer.dto import CustomerDTO
from modules.customer.ui.customer_detail_popup import CustomerDetailPopup
from modules.customer.ui.customer_dialog import CustomerDialog
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class CustomerListView(QWidget):
    def __init__(self, controller: CustomerController) -> None:
        super().__init__()
        self._controller = controller
        self._customers: list[CustomerDTO] = []

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Tim theo ten hoac so dien thoai")
        self._search_input.textChanged.connect(self._apply_filter)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Ten khach", "Dien thoai", "Cong no", "Tong mua"])
        configure_table_widget(self._table)
        self._table.itemDoubleClicked.connect(self._open_detail_for_selected)

        create_button = QPushButton("Tao khach")
        create_button.clicked.connect(self._open_create_dialog)
        edit_button = QPushButton("Sua")
        edit_button.clicked.connect(self._open_edit_dialog)
        view_button = QPushButton("Xem")
        view_button.clicked.connect(self._open_detail_for_selected)
        refresh_button = QPushButton("Tai lai")
        refresh_button.clicked.connect(self.reload)

        actions = QHBoxLayout()
        actions.addWidget(self._search_input, 1)
        actions.addWidget(create_button)
        actions.addWidget(edit_button)
        actions.addWidget(view_button)
        actions.addWidget(refresh_button)

        layout = QVBoxLayout(self)
        layout.addLayout(actions)
        layout.addWidget(self._table)

        self.reload()

    def reload(self) -> None:
        try:
            self._customers = list(self._controller.list_customers())
            self._apply_filter()
        except Exception as exc:
            MessageBox.error(self, "Loi tai du lieu", str(exc))

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip()
        filtered = self._controller.search_customers(query) if query else self._customers
        self._render_rows(filtered)

    def _render_rows(self, customers: list[CustomerDTO]) -> None:
        self._table.setRowCount(len(customers))
        for row, customer in enumerate(customers):
            self._table.setItem(row, 0, QTableWidgetItem(customer.customer_name))
            self._table.setItem(row, 1, QTableWidgetItem(customer.phone or "-"))
            balance_item = QTableWidgetItem(format_money(customer.current_balance))
            if customer.current_balance < Decimal("0"):
                balance_item.setForeground(QColor("#b91c1c"))
            elif customer.current_balance > Decimal("0"):
                balance_item.setForeground(QColor("#14532d"))
            self._table.setItem(row, 2, balance_item)
            self._table.setItem(row, 3, QTableWidgetItem(format_money(customer.total_sales)))
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, customer.id)

    def _selected_customer_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _open_create_dialog(self) -> None:
        dialog = CustomerDialog(title="Tao khach hang", parent=self)
        if dialog.exec():
            payload = dialog.payload()
            phone = (payload["phone"] or "").strip()
            if phone and self._controller.is_phone_duplicate(phone):
                MessageBox.warning(self, "Canh bao", "So dien thoai da ton tai, van tiep tuc tao khach hang.")
            try:
                self._controller.create_customer(**payload)
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Khong tao duoc khach hang", str(exc))

    def _open_edit_dialog(self) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            MessageBox.warning(self, "Chua chon", "Hay chon mot khach hang de sua.")
            return
        detail = self._controller.get_customer_with_recent_invoices(customer_id)
        dialog = CustomerDialog(
            title="Sua khach hang",
            customer_name=detail.customer.customer_name,
            phone=detail.customer.phone,
            parent=self,
        )
        if dialog.exec():
            payload = dialog.payload()
            phone = (payload["phone"] or "").strip()
            if phone and self._controller.is_phone_duplicate(phone, excluding_customer_id=customer_id):
                MessageBox.warning(self, "Canh bao", "So dien thoai da ton tai, van tiep tuc cap nhat.")
            try:
                self._controller.update_customer(customer_id, **payload)
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Khong cap nhat duoc khach hang", str(exc))

    def _open_detail_for_selected(self, *_args: object) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            return
        try:
            detail = self._controller.get_customer_with_recent_invoices(customer_id)
            CustomerDetailPopup(detail, self).exec()
        except Exception as exc:
            MessageBox.error(self, "Khong tai duoc chi tiet", str(exc))
