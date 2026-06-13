from __future__ import annotations

from decimal import Decimal
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout

from modules.customer.controller import CustomerController, CustomerDetailData
from modules.customer.ui.customer_dialog import CustomerDialog
from modules.customer.ui.debt_payment_dialog import DebtPaymentDialog
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget
from shared.widgets.ui_scale import apply_large_ui, boost_font_size


class CustomerDetailPopup(QDialog):
    def __init__(
        self,
        detail: CustomerDetailData,
        parent: QDialog | None = None,
        *,
        controller: CustomerController | None = None,
        on_updated: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._detail = detail
        self._controller = controller
        self._on_updated = on_updated

        self.setWindowTitle("Chi tiết khách hàng")
        self.resize(980, 640)
        self.setMinimumSize(860, 560)
        self.setObjectName("customerDetailPopup")

        customer = detail.customer
        balance_color = "#b91c1c" if customer.current_balance < Decimal("0") else "#0f766e"

        header_title = QLabel(customer.customer_name)
        header_title.setObjectName("customerDetailTitle")
        header_subtitle = QLabel(
            f"{customer.phone or 'Không có số điện thoại'}  |  {customer.address or 'Không có địa chỉ'}"
        )
        header_subtitle.setProperty("class", "muted")

        debt_chip = QLabel(f"Công nợ hiện tại: {customer.current_balance:,.0f}")
        debt_chip.setObjectName("customerDebtChip")
        debt_chip.setStyleSheet(
            f"color: {balance_color}; font-size: {boost_font_size(16)}px; font-weight: 700;"
            "background: rgba(139, 94, 60, 0.08); border-radius: 14px; padding: 8px 12px;"
        )
        total_sales_label = QLabel(f"Tổng mua: {format_money(customer.total_sales)}")
        total_sales_label.setObjectName("customerTotalSales")

        note_title = QLabel("Ghi chú")
        note_title.setObjectName("customerSectionTitle")
        note_value_label = QLabel(customer.note or "-")
        note_value_label.setWordWrap(True)
        note_value_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        note_value_label.setObjectName("customerNoteValue")

        history_title = QLabel("Lịch sử giao dịch gần nhất")
        history_title.setObjectName("customerSectionTitle")
        history_table = QTableWidget(0, 4)
        history_table.setHorizontalHeaderLabels(["Thời điểm", "Loại giao dịch", "Hàng đã giao dịch", "Số tiền"])
        configure_table_widget(history_table, "customer.detail.history")
        history_table.setMinimumHeight(240)
        history_table.itemDoubleClicked.connect(self._open_transaction_from_history)
        self._history_table = history_table
        history_empty_label = QLabel("Chưa có giao dịch nào gần đây.")
        history_empty_label.setProperty("class", "muted")
        history_empty_label.setVisible(not detail.recent_history)
        history_table.setVisible(bool(detail.recent_history))
        for row, entry in enumerate(detail.recent_history):
            history_table.insertRow(row)
            history_table.setItem(row, 0, QTableWidgetItem(format_datetime(entry.transaction_datetime)))
            history_table.setItem(row, 1, QTableWidgetItem(entry.transaction_type))
            history_table.setItem(row, 2, QTableWidgetItem(entry.item_summary))
            history_table.setItem(row, 3, QTableWidgetItem(format_money(entry.amount)))
            history_table.item(row, 0).setData(Qt.ItemDataRole.UserRole, (entry.transaction_kind, entry.transaction_id))

        actions_layout = QHBoxLayout()
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(8)
        if self._controller is not None:
            edit_button = QPushButton("Sửa")
            edit_button.clicked.connect(self._edit_customer)
            delete_button = QPushButton("Xóa")
            delete_button.clicked.connect(self._delete_customer)
            debt_button = QPushButton("Thanh toán nợ")
            debt_button.clicked.connect(self._pay_debt)
            actions_layout.addWidget(edit_button)
            actions_layout.addWidget(delete_button)
            actions_layout.addWidget(debt_button)
        actions_layout.addStretch()

        header_layout = QVBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(4)
        header_layout.addWidget(header_title)
        header_layout.addWidget(header_subtitle)

        summary_layout = QHBoxLayout()
        summary_layout.setContentsMargins(0, 0, 0, 0)
        summary_layout.setSpacing(10)
        summary_layout.addWidget(debt_chip, 0)
        summary_layout.addWidget(total_sales_label, 0)
        summary_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addLayout(header_layout)
        layout.addLayout(summary_layout)
        layout.addLayout(actions_layout)
        layout.addWidget(note_title)
        layout.addWidget(note_value_label)
        layout.addWidget(history_title)
        layout.addWidget(history_empty_label)
        layout.addWidget(history_table)
        apply_large_ui(self)
        self.setStyleSheet(
            self.styleSheet()
            + f"""
QDialog#customerDetailPopup {{
    background: #f8fafc;
}}
QLabel#customerDetailTitle {{
    font-size: {boost_font_size(22)}px;
    font-weight: 700;
    color: #0f172a;
}}
QLabel#customerSectionTitle {{
    font-size: {boost_font_size(15)}px;
    font-weight: 700;
    color: #334155;
    margin-top: 4px;
}}
QLabel#customerNoteValue,
QLabel#customerTotalSales {{
    font-size: {boost_font_size(16)}px;
    color: #0f172a;
}}
QTableWidget {{
    font-size: {boost_font_size(15)}px;
    background: white;
    border: 1px solid #dbe4ee;
    border-radius: 10px;
    gridline-color: #edf2f7;
    alternate-background-color: #f8fafc;
}}
QHeaderView::section {{
    background: #f2ece6;
    color: #5b4636;
    font-weight: 700;
    border: none;
    border-bottom: 1px solid #d9c6b3;
    padding: 10px 8px;
}}
QPushButton {{
    min-height: 40px;
    border-radius: 10px;
    padding: 8px 14px;
}}
"""
        )

    def _edit_customer(self) -> None:
        if self._controller is None:
            return
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
                    balance_transaction_datetime=payload["balance_transaction_datetime"],
                )
                self._handle_updated()
                MessageBox.info(self, "Thành công", "Đã cập nhật khách hàng.")
                self.accept()
            except Exception as exc:
                MessageBox.error(self, "Không cập nhật được khách hàng", str(exc))

    def _delete_customer(self) -> None:
        if self._controller is None:
            return
        customer = self._detail.customer
        delete_mode = self._controller.get_delete_mode(customer.id)
        if delete_mode == "deactivate":
            confirm_message = (
                "Khách hàng này đã có lịch sử giao dịch. Không thể xóa vĩnh viễn, "
                "hệ thống sẽ chuyển khách sang trạng thái ngừng sử dụng và ẩn khỏi danh sách mặc định. "
                "Bạn có muốn tiếp tục không?"
            )
        else:
            confirm_message = f"Xóa vĩnh viễn khách hàng '{customer.customer_name}'?"
        confirmed = QMessageBox.question(
            self,
            "Xác nhận xóa",
            confirm_message,
        )
        if confirmed != QMessageBox.StandardButton.Yes:
            return
        try:
            result = self._controller.delete_customer(customer.id)
            self._handle_updated()
            message = (
                "Đã chuyển khách hàng sang trạng thái ngừng sử dụng. Lịch sử giao dịch vẫn được giữ lại."
                if result.action == "deactivated"
                else "Đã xóa khách hàng."
            )
            MessageBox.info(self, "Thành công", message)
            self.accept()
        except Exception as exc:
            MessageBox.error(self, "Không xóa được khách hàng", str(exc))

    def _pay_debt(self) -> None:
        if self._controller is None:
            return
        customer = self._detail.customer
        dialog = DebtPaymentDialog(customer, self)
        if dialog.exec():
            try:
                payload = dialog.payload()
                self._controller.pay_debt(
                    customer.id,
                    Decimal(payload["amount"]),
                    note=payload["note"],
                    payment_datetime=payload["payment_datetime"],
                )
                self._handle_updated()
                MessageBox.info(self, "Thành công", "Đã ghi nhận thanh toán nợ.")
                self.accept()
            except Exception as exc:
                MessageBox.error(self, "Không ghi nhận được thanh toán nợ", str(exc))

    def _open_transaction_from_history(self, *_args: object) -> None:
        row = self._history_table.currentRow()
        if row < 0:
            return
        payload = self._history_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if payload is None:
            return
        target = self._find_history_navigation_target()
        if target is not None:
            transaction_kind, transaction_id = payload
            target.navigate_to_history_transaction(transaction_kind, transaction_id)
            self.accept()

    def _handle_updated(self) -> None:
        if self._on_updated is not None:
            self._on_updated()

    def _find_history_navigation_target(self) -> object | None:
        current = self.parentWidget()
        while current is not None:
            if hasattr(current, "navigate_to_history_transaction"):
                return current
            current = current.parentWidget()
        top_level = self.window()
        if hasattr(top_level, "navigate_to_history_transaction"):
            return top_level
        return None
