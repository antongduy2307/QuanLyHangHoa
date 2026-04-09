from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from modules.returns.controller import SourceInvoiceSearchRow
from shared.widgets.autocomplete_line_edit import AutocompleteLineEdit


class SourceInvoiceSearchWidget(QWidget):
    invoice_selected = pyqtSignal(int)
    search_requested = pyqtSignal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._results: list[SourceInvoiceSearchRow] = []

        self.search_input = AutocompleteLineEdit()
        self.search_input.setPlaceholderText("Nhập mã hóa đơn nguồn")
        self.search_input.textChanged.connect(self._emit_search_requested)
        self.search_input.suggestion_selected.connect(self._emit_selected_by_id)

        self.search_button = QPushButton("Tìm")
        self.search_button.clicked.connect(lambda: self.search_requested.emit(self.search_input.text()))

        header = QHBoxLayout()
        header.addWidget(self.search_input, 1)
        header.addWidget(self.search_button)

        layout = QVBoxLayout(self)
        layout.addLayout(header)

    def set_results(self, rows: list[SourceInvoiceSearchRow]) -> None:
        self._results = rows
        suggestions = [(f"{row.invoice_code} | {row.customer_label}", row.invoice_id) for row in rows]
        self.search_input.set_suggestions(suggestions)

    def _emit_search_requested(self) -> None:
        self.search_requested.emit(self.search_input.text())

    def _emit_selected_by_id(self, invoice_id: object) -> None:
        if invoice_id is not None:
            self.invoice_selected.emit(int(invoice_id))
