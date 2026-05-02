from __future__ import annotations

from decimal import Decimal

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QShowEvent
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)

from modules.customer.controller import CustomerController, CustomerDebtEntry, CustomerDetailData, CustomerHistoryEntry
from modules.customer.dto import CustomerDTO
from modules.customer.ui.customer_dialog import CustomerDialog
from modules.customer.ui.debt_payment_dialog import DebtPaymentDialog
from modules.customer.ui.debt_payment_detail_popup import DebtPaymentDetailPopup
from modules.returns.ui.return_detail_popup import ReturnDetailPopup
from modules.sales.ui.invoice_detail_popup import InvoiceDetailPopup
from shared.formatting.dates import format_datetime, format_datetime_seconds
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget


class _PagedTableSection(QWidget):
    def __init__(self, headers: list[str], persistence_key: str, page_size: int = 7, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._entries: list[object] = []
        self._page = 0
        self._page_size = page_size

        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        configure_table_widget(self.table, persistence_key)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.table.setMinimumHeight(360)

        self._page_label = QLabel("")
        self._page_label.setObjectName("pagerLabel")
        self._prev_button = QPushButton("‹")
        self._next_button = QPushButton("›")
        for button in (self._prev_button, self._next_button):
            button.setObjectName("pagerButton")
            button.setFixedSize(28, 28)
        self._prev_button.clicked.connect(self._go_prev)
        self._next_button.clicked.connect(self._go_next)

        footer = QHBoxLayout()
        footer.setContentsMargins(0, 0, 0, 0)
        footer.setSpacing(6)
        footer.addWidget(self._prev_button)
        footer.addWidget(self._page_label)
        footer.addWidget(self._next_button)
        footer.addStretch()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(self.table)
        layout.addLayout(footer)

    def set_entries(self, entries: list[object]) -> None:
        self._entries = entries
        self._page = 0
        self._render()

    def current_entry(self) -> object | None:
        row = self.table.currentRow()
        if row < 0:
            return None
        start = self._page * self._page_size
        index = start + row
        if 0 <= index < len(self._entries):
            return self._entries[index]
        return None

    def _go_prev(self) -> None:
        if self._page > 0:
            self._page -= 1
            self._render()

    def _go_next(self) -> None:
        if (self._page + 1) * self._page_size < len(self._entries):
            self._page += 1
            self._render()

    def _render(self) -> None:
        start = self._page * self._page_size
        end = start + self._page_size
        visible = self._entries[start:end]
        self.table.setRowCount(len(visible))
        for row_index, entry in enumerate(visible):
            self._render_entry(row_index, entry)
        self._apply_table_height()
        total_pages = max(1, (len(self._entries) + self._page_size - 1) // self._page_size)
        self._page_label.setText(f"{self._page + 1}/{total_pages}")
        self._prev_button.setEnabled(self._page > 0)
        self._next_button.setEnabled((self._page + 1) * self._page_size < len(self._entries))

    def _render_entry(self, row_index: int, entry: object) -> None:
        raise NotImplementedError

    def _apply_table_height(self) -> None:
        row_height = max(self.table.verticalHeader().defaultSectionSize(), 1)
        header_height = max(self.table.horizontalHeader().height(), self.table.horizontalHeader().minimumHeight(), 1)
        frame = self.table.frameWidth() * 2
        table_height = header_height + (self._page_size * row_height) + frame + 2
        self.table.setFixedHeight(table_height)


class _TradeHistorySection(_PagedTableSection):
    def __init__(self, entries: list[CustomerHistoryEntry], on_open_detail, parent: QWidget | None = None) -> None:
        super().__init__(["Thời gian", "Loại giao dịch", "Hàng đã giao dịch", "Giá trị"], "customer.inline.trade_history", parent=parent)
        self._all_entries = entries
        self._on_open_detail = on_open_detail
        self._filter_combo = QComboBox()
        self._filter_combo.addItem("Tất cả", "ALL")
        self._filter_combo.addItem("Bán hàng", "INVOICE")
        self._filter_combo.addItem("Trả hàng", "RETURN")
        self._filter_combo.currentIndexChanged.connect(self._apply_filter)
        self.table.itemDoubleClicked.connect(self._open_selected)
        self.layout().insertWidget(0, self._filter_combo)
        self._apply_filter()

    def _apply_filter(self) -> None:
        filter_value = str(self._filter_combo.currentData())
        if filter_value == "ALL":
            self.set_entries(list(self._all_entries))
            return
        self.set_entries([entry for entry in self._all_entries if entry.transaction_kind == filter_value])

    def _open_selected(self, *_args: object) -> None:
        entry = self.current_entry()
        if isinstance(entry, CustomerHistoryEntry):
            self._on_open_detail(entry.transaction_kind, entry.transaction_id)

    def _render_entry(self, row_index: int, entry: CustomerHistoryEntry) -> None:
        self.table.setItem(row_index, 0, QTableWidgetItem(format_datetime(entry.transaction_datetime)))
        self.table.setItem(row_index, 1, QTableWidgetItem(entry.transaction_type))
        self.table.setItem(row_index, 2, QTableWidgetItem(entry.item_summary))
        self.table.setItem(row_index, 3, QTableWidgetItem(format_money(entry.amount)))


class _DebtHistorySection(_PagedTableSection):
    def __init__(self, entries: list[CustomerDebtEntry], current_balance: Decimal, on_open_detail, on_pay_debt, parent: QWidget | None = None) -> None:
        super().__init__(["Thời gian", "Loại giao dịch", "Giá trị", "Dư nợ khách hàng"], "customer.inline.debt_history", parent=parent)
        self._on_open_detail = on_open_detail
        self.table.itemDoubleClicked.connect(self._open_selected)
        self._summary_label = QLabel(f"Tổng công nợ hiện tại: {format_money(current_balance)}")
        self._summary_label.setProperty("class", "muted")
        self._pay_button = QPushButton("Thanh toán")
        self._pay_button.setObjectName("inlineActionButton")
        self._pay_button.setFixedHeight(32)
        self._pay_button.setMaximumHeight(32)
        self._pay_button.clicked.connect(on_pay_debt)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(8)
        top_row.addWidget(self._summary_label)
        top_row.addStretch()
        self.layout().insertLayout(0, top_row)

        bottom_row = QHBoxLayout()
        bottom_row.setContentsMargins(0, 0, 0, 0)
        bottom_row.setSpacing(8)
        bottom_row.addStretch()
        bottom_row.addWidget(self._pay_button)
        self.layout().addLayout(bottom_row)

        self.set_entries(entries)

    def _open_selected(self, *_args: object) -> None:
        entry = self.current_entry()
        if isinstance(entry, CustomerDebtEntry):
            self._on_open_detail(entry.transaction_kind, entry.transaction_id)

    def _render_entry(self, row_index: int, entry: CustomerDebtEntry) -> None:
        self.table.setItem(row_index, 0, QTableWidgetItem(format_datetime_seconds(entry.transaction_datetime)))
        self.table.setItem(row_index, 1, QTableWidgetItem(entry.transaction_type))
        self.table.setItem(row_index, 2, QTableWidgetItem(format_money(entry.amount)))
        self.table.setItem(row_index, 3, QTableWidgetItem(format_money(entry.balance_after)))


class _CustomerInlineDetailWidget(QFrame):
    def __init__(
        self,
        controller: CustomerController,
        detail: CustomerDetailData,
        on_changed,
        on_open_transaction,
        on_edit_transaction,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._detail = detail
        self._on_changed = on_changed
        self._on_open_transaction = on_open_transaction
        self._on_edit_transaction = on_edit_transaction
        self.setObjectName("customerInlineDetail")
        self.setFrameShape(QFrame.Shape.NoFrame)

        customer = detail.customer
        self._trade_entries = list(controller.list_customer_trade_history(customer.id))
        self._debt_entries = list(controller.list_customer_debt_history(customer.id))

        tabs = QTabWidget()
        tabs.addTab(self._build_general_tab(), "Thông tin chung")
        tabs.addTab(self._build_trade_tab(), "Lịch sử bán/trả hàng")
        tabs.addTab(self._build_debt_tab(), "Nợ cần thu từ khách")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)
        layout.addWidget(tabs)

        self.setStyleSheet(
            """
QFrame#customerInlineDetail {
    background: #ffffff;
    border: 1px solid #dbe4ee;
    border-radius: 12px;
}
QPushButton#inlineActionButton {
    min-width: 76px;
    max-width: 112px;
    min-height: 32px;
    max-height: 32px;
    padding: 4px 10px;
    border-radius: 8px;
}
QPushButton#pagerButton {
    min-width: 28px;
    max-width: 28px;
    min-height: 28px;
    max-height: 28px;
    padding: 0;
    border-radius: 8px;
}
QLabel#pagerLabel {
    min-width: 42px;
}
"""
        )

    def _build_general_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        customer = self._detail.customer
        layout.addWidget(QLabel(f"Tên: {customer.customer_name}"))
        layout.addWidget(QLabel(f"Số điện thoại: {customer.phone or '-'}"))
        layout.addWidget(QLabel(f"Địa chỉ: {customer.address or '-'}"))
        layout.addWidget(QLabel(f"Ghi chú: {customer.note or '-'}"))

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        edit_button = QPushButton("Sửa")
        edit_button.setObjectName("inlineActionButton")
        edit_button.setFixedHeight(32)
        edit_button.setMaximumHeight(32)
        edit_button.clicked.connect(self._edit_customer)
        delete_button = QPushButton("Xóa")
        delete_button.setObjectName("inlineActionButton")
        delete_button.setFixedHeight(32)
        delete_button.setMaximumHeight(32)
        delete_button.clicked.connect(self._delete_customer)
        actions.addWidget(edit_button)
        actions.addWidget(delete_button)
        actions.addStretch()
        layout.addLayout(actions)
        layout.addStretch()
        return widget

    def _build_trade_tab(self) -> QWidget:
        return _TradeHistorySection(self._trade_entries, self._open_transaction_popup)

    def _build_debt_tab(self) -> QWidget:
        return _DebtHistorySection(
            self._debt_entries,
            self._detail.customer.current_balance,
            self._open_transaction_popup,
            self._pay_debt,
        )

    def _edit_customer(self) -> None:
        customer = self._detail.customer
        dialog = CustomerDialog(
            title="Sửa khách hàng",
            customer_name=customer.customer_name,
            phone=customer.phone,
            address=customer.address,
            note=customer.note,
            current_balance=customer.current_balance,
            edit_mode=True,
            parent=self,
        )
        if dialog.exec():
            try:
                payload = dialog.payload()
                self._controller.update_customer(
                    customer.id,
                    customer_name=str(payload["customer_name"]),
                    phone=payload["phone"],
                    address=payload["address"],
                    note=payload["note"],
                    current_balance=Decimal(payload["current_balance"]),
                )
                MessageBox.info(self, "Thành công", "Đã cập nhật khách hàng.")
                self._on_changed()
            except Exception as exc:
                MessageBox.error(self, "Không cập nhật được khách hàng", str(exc))

    def _delete_customer(self) -> None:
        customer = self._detail.customer
        confirmed = QMessageBox.question(
            self,
            "Xác nhận xóa",
            (
                f"Xóa khách hàng '{customer.customer_name}'?\n\n"
                "Khách chưa phát sinh nghiệp vụ sẽ bị xóa vĩnh viễn. "
                "Khách đã có hóa đơn, trả hàng hoặc lịch sử công nợ sẽ bị chặn xóa."
            ),
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            self._controller.delete_customer(customer.id)
            MessageBox.info(self, "Thành công", "Đã xóa khách hàng.")
            self._on_changed()
        except Exception as exc:
            MessageBox.error(self, "Không xóa được khách hàng", str(exc))

    def _pay_debt(self) -> None:
        dialog = DebtPaymentDialog(self._detail.customer, self)
        if dialog.exec():
            try:
                payload = dialog.payload()
                self._controller.pay_debt(
                    self._detail.customer.id,
                    Decimal(payload["amount"]),
                    note=payload["note"],
                    payment_datetime=payload["payment_datetime"],
                )
                MessageBox.info(self, "Thành công", "Đã ghi nhận thanh toán nợ.")
                self._on_changed()
            except Exception as exc:
                MessageBox.error(self, "Không ghi nhận được thanh toán nợ", str(exc))

    def _open_transaction_popup(self, transaction_kind: str, transaction_id: int) -> None:
        def _open_record() -> None:
            self._on_open_transaction(transaction_kind, transaction_id)

        def _edit_record() -> None:
            self._on_edit_transaction(transaction_kind, transaction_id)

        try:
            if transaction_kind == "INVOICE":
                from modules.sales.controller import SalesController

                controller = SalesController(self._controller._session_factory)
                invoice = controller.get_invoice_detail(transaction_id)
                InvoiceDetailPopup(
                    invoice,
                    self,
                    controller=controller,
                    on_open_record=_open_record,
                    on_edit_record=_edit_record,
                ).exec()
            elif transaction_kind == "RETURN":
                from modules.returns.controller import ReturnController

                controller = ReturnController(self._controller._session_factory)
                return_invoice = controller.get_return_invoice_detail(transaction_id)
                ReturnDetailPopup(
                    return_invoice,
                    self,
                    controller=controller,
                    on_open_record=_open_record,
                    on_edit_record=_edit_record,
                ).exec()
            elif transaction_kind == "DEBT_PAYMENT":
                ledger = self._controller.get_debt_payment_detail(transaction_id)
                DebtPaymentDetailPopup(ledger, self, controller=self._controller, on_open_record=_open_record).exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được chi tiết giao dịch", str(exc))


class CustomerListView(QWidget):
    transaction_changed = pyqtSignal()

    def __init__(self, controller: CustomerController) -> None:
        super().__init__()
        self._controller = controller
        self._customers: list[CustomerDTO] = []
        self._expanded_customer_id: int | None = None
        self.setObjectName("customerListRoot")

        self._search_input = QLineEdit()
        self._search_input.setObjectName("customerSearchInput")
        self._search_input.setPlaceholderText("Tìm theo tên khách hàng")
        self._search_input.textChanged.connect(self._apply_filter)

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

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Tên khách", "Điện thoại", "Công nợ", "Tổng mua"])
        configure_table_widget(self._table, "customer.list")
        self._table.setAlternatingRowColors(True)
        self._table.cellClicked.connect(self._handle_table_click)

        self._create_button = QPushButton("+ Tạo khách")
        self._create_button.setObjectName("customerCreateButton")
        self._create_button.clicked.connect(self._open_create_dialog)

        self._side_panel = QFrame()
        self._side_panel.setObjectName("customerSidePanel")
        self._side_panel.setProperty("class", "panel")
        side_layout = QVBoxLayout(self._side_panel)
        side_layout.setContentsMargins(12, 12, 12, 12)
        side_layout.setSpacing(10)
        side_layout.addWidget(QLabel("Tạo mới"))
        side_layout.addWidget(self._create_button)
        side_layout.addSpacing(10)
        side_layout.addWidget(QLabel("Sắp xếp"))
        side_layout.addWidget(self._sort_combo)
        side_layout.addSpacing(10)
        side_layout.addWidget(QLabel("Bộ lọc"))
        side_layout.addWidget(self._only_debt_checkbox)
        side_layout.addStretch()
        self._side_panel.setMaximumWidth(188)

        self._main_panel = QWidget()
        self._main_panel.setObjectName("customerMainPanel")
        main_layout = QVBoxLayout(self._main_panel)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(10)
        main_layout.addWidget(self._search_input)
        main_layout.addWidget(self._table, 1)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(self._side_panel)
        layout.addWidget(self._main_panel, 1)

        self.setStyleSheet(
            """
QWidget#customerListRoot {
    background: #f8fafc;
}
QFrame#customerSidePanel {
    background: white;
    border: 1px solid #dbe4ee;
    border-radius: 12px;
}
QWidget#customerMainPanel {
    background: transparent;
}
QLineEdit#customerSearchInput {
    background: white;
    border: 1px solid #dbe4ee;
    border-radius: 12px;
    padding: 10px 14px;
}
QTableWidget {
    background: white;
    border: 1px solid #dbe4ee;
    border-radius: 12px;
    gridline-color: #eef2f7;
    alternate-background-color: #f8fafc;
}
QHeaderView::section {
    background: #f1f5f9;
    color: #334155;
    border: none;
    border-bottom: 1px solid #dbe4ee;
    padding: 10px 8px;
    font-weight: 700;
}
"""
        )

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
        if self._expanded_customer_id is not None and not any(customer.id == self._expanded_customer_id for customer in filtered):
            self._expanded_customer_id = None
        self._render_rows(filtered)

    def _render_rows(self, customers: list[CustomerDTO]) -> None:
        summary_row_count = 1
        expanded_index = next((index for index, customer in enumerate(customers) if customer.id == self._expanded_customer_id), -1)
        total_rows = len(customers) + summary_row_count + (1 if expanded_index >= 0 else 0)
        self._table.clearSpans()
        self._table.setRowCount(total_rows)
        default_row_height = max(self._table.verticalHeader().defaultSectionSize(), 52)
        for row_index in range(total_rows):
            self._table.setRowHeight(row_index, default_row_height)
            for column in range(self._table.columnCount()):
                self._table.removeCellWidget(row_index, column)

        for column in range(self._table.columnCount()):
            item = QTableWidgetItem("")
            item.setBackground(QColor("#f4eadf"))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self._table.setItem(0, column, item)
        total_debt = sum((customer.current_balance for customer in customers), start=Decimal("0"))
        total_sales = sum((customer.total_sales for customer in customers), start=Decimal("0"))
        debt_summary = self._table.item(0, 2)
        sales_summary = self._table.item(0, 3)
        if debt_summary is not None:
            debt_summary.setText(format_money(total_debt))
            debt_summary.setForeground(QColor("#6f4628"))
        if sales_summary is not None:
            sales_summary.setText(format_money(total_sales))
            sales_summary.setForeground(QColor("#6f4628"))

        for index, customer in enumerate(customers):
            actual_row = index + summary_row_count + (1 if expanded_index >= 0 and index > expanded_index else 0)
            self._table.setItem(actual_row, 0, QTableWidgetItem(customer.customer_name))
            self._table.setItem(actual_row, 1, QTableWidgetItem(customer.phone or "-"))
            balance_item = QTableWidgetItem(format_money(customer.current_balance))
            if customer.current_balance < Decimal("0"):
                balance_item.setForeground(QColor("#b91c1c"))
            elif customer.current_balance > Decimal("0"):
                balance_item.setForeground(QColor("#0f766e"))
            self._table.setItem(actual_row, 2, balance_item)
            self._table.setItem(actual_row, 3, QTableWidgetItem(format_money(customer.total_sales)))
            self._table.item(actual_row, 0).setData(Qt.ItemDataRole.UserRole, customer.id)

        if expanded_index >= 0:
            detail_row = expanded_index + summary_row_count + 1
            customer = customers[expanded_index]
            detail = self._controller.get_customer_with_recent_history(customer.id)
            detail_widget = _CustomerInlineDetailWidget(
                self._controller,
                detail,
                on_changed=self._handle_customer_updated,
                on_open_transaction=self._open_transaction_in_history,
                on_edit_transaction=self._open_transaction_editor,
            )
            self._table.setSpan(detail_row, 0, 1, self._table.columnCount())
            self._table.setItem(detail_row, 0, QTableWidgetItem(""))
            self._table.setCellWidget(detail_row, 0, detail_widget)
            self._table.setRowHeight(detail_row, 560)

    def _handle_table_click(self, row: int, column: int) -> None:
        del column
        if row == 0:
            self._table.clearSelection()
            return
        item = self._table.item(row, 0)
        if item is None:
            return
        customer_id = item.data(Qt.ItemDataRole.UserRole)
        if customer_id is None:
            return
        if self._expanded_customer_id == customer_id:
            self._expanded_customer_id = None
            self._render_rows(self._customers)
            return
        self._expanded_customer_id = int(customer_id)
        self._render_rows(self._customers)

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
                    note=payload["note"],
                    initial_balance=Decimal(payload["initial_balance"]),
                )
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Không tạo được khách hàng", str(exc))

    def _handle_customer_updated(self) -> None:
        self.transaction_changed.emit()
        self.reload()

    def _open_transaction_in_history(self, transaction_kind: str, transaction_id: int) -> None:
        app_window = self.window()
        if hasattr(app_window, "navigate_to_history_transaction"):
            app_window.navigate_to_history_transaction(transaction_kind, transaction_id)

    def _open_transaction_editor(self, transaction_kind: str, transaction_id: int) -> None:
        app_window = self.window()
        if transaction_kind == "INVOICE" and hasattr(app_window, "open_sales_invoice_editor"):
            app_window.open_sales_invoice_editor(transaction_id)
            return
        if transaction_kind == "RETURN" and hasattr(app_window, "open_sales_return_editor"):
            app_window.open_sales_return_editor(transaction_id)
