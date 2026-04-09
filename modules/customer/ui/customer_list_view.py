from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QShowEvent
from PyQt6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from modules.customer.controller import CustomerController
from modules.customer.dto import CustomerDTO
from modules.customer.ui.customer_detail_popup import CustomerDetailPopup
from modules.customer.ui.customer_dialog import CustomerDialog
from modules.customer.ui.debt_payment_dialog import DebtPaymentDialog
from shared.formatting.money import format_money
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class CustomerListView(QWidget):
    def __init__(self, controller: CustomerController) -> None:
        super().__init__()
        self._controller = controller
        self._customers: list[CustomerDTO] = []

        self._search_input = AutocompleteLineEdit()
        self._search_input.setPlaceholderText("Tìm theo tên hoặc số điện thoại")
        self._search_input.textChanged.connect(self._apply_filter)
        self._search_input.suggestion_selected.connect(self._handle_search_suggestion_selected)

        self._sort_combo = QComboBox()
        self._sort_combo.addItem("Tên A-Z", "name_asc")
        self._sort_combo.addItem("Tên Z-A", "name_desc")
        self._sort_combo.addItem("Công nợ tăng dần", "balance_asc")
        self._sort_combo.addItem("Công nợ giảm dần", "balance_desc")
        self._sort_combo.addItem("Tổng bán tăng dần", "sales_asc")
        self._sort_combo.addItem("Tổng bán giảm dần", "sales_desc")
        self._sort_combo.currentIndexChanged.connect(self._apply_filter)

        self._only_debt_checkbox = QCheckBox("Chỉ hiện khách đang nợ")
        self._only_debt_checkbox.toggled.connect(self._apply_filter)

        self._table = QTableWidget(0, 5)
        self._table.setHorizontalHeaderLabels(["Tên khách", "Điện thoại", "Địa chỉ", "Công nợ", "Tổng mua"])
        configure_table_widget(self._table, "customer.list")
        self._table.itemDoubleClicked.connect(self._open_detail_for_selected)

        create_button = QPushButton("Tạo khách")
        create_button.clicked.connect(self._open_create_dialog)
        edit_button = QPushButton("Sửa")
        edit_button.clicked.connect(self._open_edit_dialog)
        payment_button = QPushButton("Thanh toán nợ")
        payment_button.clicked.connect(self._open_debt_payment_dialog)
        view_button = QPushButton("Xem")
        view_button.clicked.connect(self._open_detail_for_selected)
        refresh_button = QPushButton("Tải lại")
        refresh_button.clicked.connect(self.reload)

        actions = QHBoxLayout()
        actions.addWidget(self._search_input, 1)
        actions.addWidget(self._sort_combo)
        actions.addWidget(self._only_debt_checkbox)
        actions.addWidget(create_button)
        actions.addWidget(edit_button)
        actions.addWidget(payment_button)
        actions.addWidget(view_button)
        actions.addWidget(refresh_button)

        layout = QVBoxLayout(self)
        layout.addLayout(actions)
        layout.addWidget(self._table)

        self.reload()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self.reload()

    def reload(self) -> None:
        try:
            self._customers = list(self._controller.list_customers(self._current_sort_option(), self._only_debt_checkbox.isChecked()))
            self._apply_filter()
        except Exception as exc:
            MessageBox.error(self, "Lỗi tải dữ liệu", str(exc))

    def _current_sort_option(self) -> str:
        return str(self._sort_combo.currentData())

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip()
        sort_option = self._current_sort_option()
        only_positive_debt = self._only_debt_checkbox.isChecked()
        filtered = self._controller.search_customers(query, sort_option, only_positive_debt) if query else self._controller.list_customers(sort_option, only_positive_debt)
        self._customers = filtered
        self._render_rows(filtered)
        self._update_search_suggestions(query, filtered)

    def _update_search_suggestions(self, query: str, customers: list[CustomerDTO]) -> None:
        if not query:
            self._search_input.hide_suggestions()
            return
        suggestions: list[tuple[str, object]] = []
        for customer in customers[:20]:
            label = customer.customer_name if not customer.phone else f"{customer.customer_name} | {customer.phone}"
            suggestions.append((label, customer.id))
        self._search_input.set_suggestions(suggestions)

    def _handle_search_suggestion_selected(self, customer_id: object) -> None:
        if customer_id is None:
            return
        self._select_customer_row(int(customer_id))

    def _select_customer_row(self, customer_id: int) -> None:
        for row_index in range(self._table.rowCount()):
            item = self._table.item(row_index, 0)
            if item is not None and item.data(Qt.ItemDataRole.UserRole) == customer_id:
                self._table.setCurrentCell(row_index, 0)
                break

    def _render_rows(self, customers: list[CustomerDTO]) -> None:
        self._table.setRowCount(len(customers))
        for row, customer in enumerate(customers):
            self._table.setItem(row, 0, QTableWidgetItem(customer.customer_name))
            self._table.setItem(row, 1, QTableWidgetItem(customer.phone or "-"))
            self._table.setItem(row, 2, QTableWidgetItem(customer.address or "-"))
            balance_item = QTableWidgetItem(format_money(customer.current_balance))
            if customer.current_balance < Decimal("0"):
                balance_item.setForeground(QColor("#b91c1c"))
            elif customer.current_balance > Decimal("0"):
                balance_item.setForeground(QColor("#14532d"))
            self._table.setItem(row, 3, balance_item)
            self._table.setItem(row, 4, QTableWidgetItem(format_money(customer.total_sales)))
            self._table.item(row, 0).setData(Qt.ItemDataRole.UserRole, customer.id)

    def _selected_customer_id(self) -> int | None:
        row = self._table.currentRow()
        if row < 0:
            return None
        item = self._table.item(row, 0)
        return None if item is None else item.data(Qt.ItemDataRole.UserRole)

    def _selected_customer(self) -> CustomerDTO | None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            return None
        return next((customer for customer in self._customers if customer.id == customer_id), None)

    def _open_create_dialog(self) -> None:
        dialog = CustomerDialog(title="Tạo khách hàng", edit_mode=False, parent=self)
        if dialog.exec():
            payload = dialog.payload()
            phone = (payload["phone"] or "").strip()
            if phone and self._controller.is_phone_duplicate(phone):
                MessageBox.warning(self, "Cảnh báo", "Số điện thoại đã tồn tại, vẫn tiếp tục tạo khách hàng.")
            try:
                self._controller.create_customer(
                    customer_name=str(payload["customer_name"]),
                    phone=payload["phone"],
                    address=payload["address"],
                    initial_balance=Decimal(payload["initial_balance"]),
                )
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Không tạo được khách hàng", str(exc))

    def _open_edit_dialog(self) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một khách hàng để sửa.")
            return
        detail = self._controller.get_customer_with_recent_invoices(customer_id)
        dialog = CustomerDialog(
            title="Sửa khách hàng",
            customer_name=detail.customer.customer_name,
            phone=detail.customer.phone,
            address=detail.customer.address,
            current_balance=detail.customer.current_balance,
            edit_mode=True,
            parent=self,
        )
        if dialog.exec():
            payload = dialog.payload()
            phone = (payload["phone"] or "").strip()
            if phone and self._controller.is_phone_duplicate(phone, excluding_customer_id=customer_id):
                MessageBox.warning(self, "Cảnh báo", "Số điện thoại đã tồn tại, vẫn tiếp tục cập nhật.")
            try:
                self._controller.update_customer(
                    customer_id,
                    customer_name=str(payload["customer_name"]),
                    phone=payload["phone"],
                    address=payload["address"],
                    current_balance=Decimal(payload["current_balance"]),
                )
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Không cập nhật được khách hàng", str(exc))

    def _open_debt_payment_dialog(self) -> None:
        customer = self._selected_customer()
        if customer is None:
            MessageBox.warning(self, "Chưa chọn", "Hãy chọn một khách hàng để thu nợ.")
            return
        dialog = DebtPaymentDialog(customer, self)
        if dialog.exec():
            try:
                payload = dialog.payload()
                self._controller.pay_debt(customer.id, Decimal(payload["amount"]), note=payload["note"])
                MessageBox.info(self, "Thành công", "Đã ghi nhận thanh toán nợ.")
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Không ghi nhận được thanh toán nợ", str(exc))

    def _open_detail_for_selected(self, *_args: object) -> None:
        customer_id = self._selected_customer_id()
        if customer_id is None:
            return
        try:
            detail = self._controller.get_customer_with_recent_invoices(customer_id)
            CustomerDetailPopup(detail, self).exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được chi tiết", str(exc))

