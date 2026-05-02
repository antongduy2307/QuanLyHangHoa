from __future__ import annotations

from decimal import Decimal
from typing import Callable

from PyQt6.QtWidgets import QDialog, QGridLayout, QHBoxLayout, QLabel, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from core.db import SessionFactory
from modules.sales.controller import SalesController
from modules.sales.models import Invoice
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money_precise
from shared.formatting.quantity import format_quantity
from shared.widgets.table_helpers import configure_table_widget
from shared.widgets.ui_scale import apply_large_ui, boost_font_size


class InvoiceDetailPopup(QDialog):
    def __init__(
        self,
        invoice: Invoice,
        parent: QDialog | None = None,
        *,
        controller: SalesController | None = None,
        on_updated: Callable[[], None] | None = None,
        on_open_record: Callable[[], None] | None = None,
        on_edit_record: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._invoice = invoice
        self._controller = controller
        self._on_updated = on_updated
        self._on_open_record = on_open_record
        self._on_edit_record = on_edit_record

        balance_after = SalesController(SessionFactory).get_invoice_balance_after(invoice)
        self.setWindowTitle(f"Hóa đơn {invoice.invoice_code}")
        self.resize(1000, 700)
        self.setMinimumSize(860, 600)
        self.setObjectName("invoiceDetailPopup")

        header_widget = self._build_header(balance_after)

        items_table = QTableWidget(0, 5)
        items_table.setHorizontalHeaderLabels(["Tên hàng", "Đơn vị", "Số lượng", "Đơn giá", "Thành tiền"])
        configure_table_widget(items_table, "customer.invoice_detail.items")
        items_table.setMinimumHeight(320)
        for row_index, item in enumerate(invoice.items):
            items_table.insertRow(row_index)
            items_table.setItem(row_index, 0, QTableWidgetItem(item.product_name_snapshot))
            items_table.setItem(row_index, 1, QTableWidgetItem(item.unit_type.value))
            items_table.setItem(row_index, 2, QTableWidgetItem(format_quantity(item.quantity)))
            items_table.setItem(row_index, 3, QTableWidgetItem(format_money_precise(item.unit_price)))
            items_table.setItem(row_index, 4, QTableWidgetItem(format_money_precise(item.line_total)))

        self._open_record_button = QPushButton("Mở phiếu")
        self._open_record_button.clicked.connect(self._open_record)
        self._open_record_button.setVisible(self._on_open_record is not None)
        self._open_record_button.setObjectName("recordOpenButton")
        self._edit_record_button = QPushButton("Sửa")
        self._edit_record_button.clicked.connect(self._edit_record)
        self._edit_record_button.setVisible(self._on_edit_record is not None)
        self._edit_record_button.setObjectName("recordActionButton")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(header_widget)
        layout.addWidget(items_table)
        if self._on_open_record is not None or self._on_edit_record is not None:
            button_row = QHBoxLayout()
            button_row.setContentsMargins(0, 0, 0, 0)
            button_row.setSpacing(8)
            button_row.addStretch()
            button_row.addWidget(self._edit_record_button)
            button_row.addWidget(self._open_record_button)
            layout.addLayout(button_row)

        apply_large_ui(self)
        self.setStyleSheet(
            self.styleSheet()
            + f"""
QDialog#invoiceDetailPopup {{
    background: #f8fafc;
}}
QLabel#detailTitle {{
    font-size: {boost_font_size(18)}px;
    font-weight: 700;
}}
QLabel#detailNote {{
    background: white;
    border: 1px solid #dbe4ee;
    border-radius: 10px;
    padding: 10px;
}}
QPushButton#recordOpenButton {{
    min-width: 96px;
    max-width: 128px;
    padding: 6px 14px;
}}
QPushButton#recordActionButton {{
    min-width: 72px;
    max-width: 112px;
    padding: 6px 14px;
}}
QTableWidget {{
    background: white;
    border: 1px solid #dbe4ee;
    border-radius: 10px;
}}
"""
        )

    def _build_header(self, balance_after: Decimal | None) -> QWidget:
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)

        left_title = QLabel("Thông tin phiếu")
        left_title.setObjectName("detailTitle")
        middle_title = QLabel("Thanh toán")
        middle_title.setObjectName("detailTitle")
        right_title = QLabel("Ghi chú")
        right_title.setObjectName("detailTitle")

        note_label = QLabel(self._invoice.note or "-")
        note_label.setWordWrap(True)
        note_label.setObjectName("detailNote")

        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        left_col.addWidget(left_title)
        left_col.addWidget(QLabel(f"Mã hóa đơn: {self._invoice.invoice_code}"))
        left_col.addWidget(QLabel(f"Thời gian: {format_datetime(self._invoice.invoice_datetime)}"))
        left_col.addWidget(QLabel(f"Khách hàng: {self._invoice.customer_snapshot_name}"))

        middle_col = QVBoxLayout()
        middle_col.setSpacing(4)
        middle_col.addWidget(middle_title)
        middle_col.addWidget(QLabel(f"Tổng tiền đơn hàng: {format_money_precise(self._invoice.total_amount)}"))
        middle_col.addWidget(QLabel(f"Khách đã trả: {format_money_precise(self._invoice.paid_amount or 0)}"))
        middle_col.addWidget(self._build_balance_after_label(balance_after))

        right_col = QVBoxLayout()
        right_col.setSpacing(4)
        right_col.addWidget(right_title)
        right_col.addWidget(note_label)

        wrapper = QWidget()
        wrapper.setLayout(grid)
        grid.addLayout(left_col, 0, 0)
        grid.addLayout(middle_col, 0, 1)
        grid.addLayout(right_col, 0, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        return wrapper

    def _open_record(self) -> None:
        if self._on_open_record is not None:
            self._on_open_record()
            self.accept()

    def _edit_record(self) -> None:
        if self._on_edit_record is not None:
            self._on_edit_record()
            self.accept()

    def _handle_updated(self) -> None:
        if self._on_updated is not None:
            self._on_updated()

    def _build_balance_after_label(self, balance_after: Decimal | None) -> QLabel:
        if self._invoice.customer_id is None or balance_after is None:
            return QLabel("Công nợ sau đơn này: -")

        color = "#b91c1c" if balance_after < Decimal("0") else "#14532d"
        return QLabel(
            f"Công nợ sau đơn này: <span style='color:{color}; font-size:{boost_font_size(16)}px;'>{format_money_precise(balance_after)}</span>"
        )
