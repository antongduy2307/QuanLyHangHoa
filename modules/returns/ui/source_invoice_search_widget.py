from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLineEdit, QListWidget, QPushButton, QVBoxLayout, QWidget

from modules.returns.controller import SourceInvoiceSearchRow


class SourceInvoiceSearchWidget(QWidget):
    invoice_selected = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._results: list[SourceInvoiceSearchRow] = []

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Nhập mã hóa đơn nguồn")
        self.search_button = QPushButton("Tìm")
        self.result_list = QListWidget()
        self.result_list.setMaximumHeight(150)
        self.result_list.itemClicked.connect(self._emit_selected)

        header = QHBoxLayout()
        header.addWidget(self.search_input, 1)
        header.addWidget(self.search_button)

        layout = QVBoxLayout(self)
        layout.addLayout(header)
        layout.addWidget(self.result_list)

    def set_results(self, rows: list[SourceInvoiceSearchRow]) -> None:
        self._results = rows
        self.result_list.clear()
        for row in rows:
            self.result_list.addItem(f"{row.invoice_code} | {row.customer_label}")
            self.result_list.item(self.result_list.count() - 1).setData(256, row.invoice_id)

    def _emit_selected(self, *_args: object) -> None:
        item = self.result_list.currentItem()
        if item is None:
            return
        invoice_id = item.data(256)
        if invoice_id is not None:
            self.invoice_selected.emit(int(invoice_id))
