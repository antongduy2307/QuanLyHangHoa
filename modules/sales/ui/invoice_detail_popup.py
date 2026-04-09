from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout

from core.db import SessionFactory
from modules.returns.controller import ReturnController
from modules.returns.ui.return_detail_popup import ReturnDetailPopup
from modules.sales.controller import SalesController
from modules.sales.models import Invoice
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.formatting.quantity import format_quantity
from shared.widgets.message_box import MessageBox
from shared.widgets.table_helpers import configure_table_widget
from shared.widgets.ui_scale import apply_large_ui


class InvoiceDetailPopup(QDialog):
    def __init__(self, invoice: Invoice, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self._invoice = invoice
        balance_after = SalesController(SessionFactory).get_invoice_balance_after(invoice)
        self.setWindowTitle(f"Hóa đơn {invoice.invoice_code}")
        self.resize(1100, 760)
        self.setMinimumSize(980, 680)

        items_table = QTableWidget(0, 6)
        items_table.setHorizontalHeaderLabels(["Mã hàng", "Tên hàng", "Đơn vị", "Số lượng", "Đơn giá", "Thành tiền"])
        configure_table_widget(items_table, "sales.invoice_detail.items")
        items_table.setMinimumHeight(320)
        for row_index, item in enumerate(invoice.items):
            items_table.insertRow(row_index)
            items_table.setItem(row_index, 0, QTableWidgetItem(item.product_code_snapshot))
            items_table.setItem(row_index, 1, QTableWidgetItem(item.product_name_snapshot))
            items_table.setItem(row_index, 2, QTableWidgetItem(item.unit_type.value))
            items_table.setItem(row_index, 3, QTableWidgetItem(format_quantity(item.quantity)))
            items_table.setItem(row_index, 4, QTableWidgetItem(format_money(item.unit_price)))
            items_table.setItem(row_index, 5, QTableWidgetItem(format_money(item.line_total)))

        self._returns_table = QTableWidget(0, 4)
        self._returns_table.setHorizontalHeaderLabels(["Mã trả hàng", "Thời điểm", "Tổng trả", "Xử lý"])
        configure_table_widget(self._returns_table, "sales.invoice_detail.returns")
        self._returns_table.setMinimumHeight(180)
        self._returns_table.itemDoubleClicked.connect(self._open_return_detail)
        self._returns_empty_label = QLabel("Chưa có phiếu trả hàng")
        self._returns_open_button = QPushButton("Xem phiếu trả")
        self._returns_open_button.clicked.connect(self._open_return_detail)

        layout = QVBoxLayout(self)
        layout.setSpacing(14)
        layout.addWidget(QLabel(f"Mã hóa đơn: {invoice.invoice_code}"))
        layout.addWidget(QLabel(f"Thời điểm: {format_datetime(invoice.invoice_datetime)}"))
        layout.addWidget(QLabel(f"Khách: {invoice.customer_snapshot_name}"))
        layout.addWidget(QLabel(f"Tổng tiền: {format_money(invoice.total_amount)}"))
        layout.addWidget(QLabel(f"Khách trả: {format_money(invoice.paid_amount or 0)}"))
        layout.addWidget(self._build_balance_after_label(balance_after))
        layout.addWidget(QLabel(f"Thanh toán: {invoice.payment_method.value if invoice.payment_method else '-'}"))
        layout.addWidget(items_table)
        layout.addWidget(QLabel("Phiếu trả hàng liên quan"))
        layout.addWidget(self._returns_empty_label)
        layout.addWidget(self._returns_table)
        layout.addWidget(self._returns_open_button)

        self._load_related_returns()
        apply_large_ui(self)
        self.setStyleSheet(self.styleSheet() + "\nQDialog QLabel { font-size: 16px; }\nQTableWidget { font-size: 15px; }\n")

    def _load_related_returns(self) -> None:
        controller = ReturnController(SessionFactory)
        try:
            returns = list(controller.list_return_invoices())
            related = [item for item in returns if item.source_invoice_id == self._invoice.id]
            self._returns_table.setRowCount(len(related))
            self._returns_empty_label.setVisible(len(related) == 0)
            self._returns_table.setVisible(len(related) > 0)
            self._returns_open_button.setVisible(len(related) > 0)
            for row_index, return_invoice in enumerate(related):
                self._returns_table.setItem(row_index, 0, QTableWidgetItem(return_invoice.return_code))
                self._returns_table.setItem(row_index, 1, QTableWidgetItem(format_datetime(return_invoice.return_datetime)))
                self._returns_table.setItem(row_index, 2, QTableWidgetItem(format_money(return_invoice.total_amount)))
                self._returns_table.setItem(row_index, 3, QTableWidgetItem(return_invoice.handling_mode.value))
                self._returns_table.item(row_index, 0).setData(256, return_invoice.id)
        except Exception as exc:
            self._returns_empty_label.setText("Không tải được phiếu trả hàng liên quan")
            self._returns_open_button.setVisible(False)
            MessageBox.error(self, "Không tải được phiếu trả hàng", str(exc))

    def _open_return_detail(self, *_args: object) -> None:
        item = self._returns_table.item(self._returns_table.currentRow(), 0)
        if item is None:
            return
        return_id = item.data(256)
        if return_id is None:
            return
        controller = ReturnController(SessionFactory)
        try:
            return_invoice = controller.get_return_invoice_detail(int(return_id))
            ReturnDetailPopup(return_invoice, self).exec()
        except Exception as exc:
            MessageBox.error(self, "Không tải được chi tiết trả hàng", str(exc))

    def _build_balance_after_label(self, balance_after: Decimal | None) -> QLabel:
        if self._invoice.customer_id is None or balance_after is None:
            return QLabel("Công nợ sau đơn này: -")

        color = "#b91c1c" if balance_after < Decimal("0") else "#14532d"
        return QLabel(
            f"Công nợ sau đơn này: <span style='color:{color}; font-size:18px;'>{format_money(balance_after)}</span>"
        )
