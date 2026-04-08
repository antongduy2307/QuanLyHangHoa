from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout

from core.exceptions import ValidationError
from modules.returns.controller import ReturnController, ReturnEditDetail
from modules.returns.ui.return_summary_widget import ReturnSummaryWidget
from modules.returns.ui.source_invoice_items_table import SourceInvoiceItemsTable
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.message_box import MessageBox


class ReturnEditDialog(QDialog):
    def __init__(self, controller: ReturnController, detail: ReturnEditDetail, parent: QDialog | None = None) -> None:
        super().__init__(parent)
        self._controller = controller
        self._detail = detail
        self.setWindowTitle(f"Sửa phiếu trả {detail.return_code}")
        self.resize(860, 620)

        self._header_label = QLabel(
            f"Phiếu trả: {detail.return_code} | Thời điểm: {format_datetime(detail.return_datetime)} | Hóa đơn gốc: {detail.source_invoice_code}"
        )
        self._header_label.setWordWrap(True)
        self._customer_label = QLabel(
            f"Khách: {detail.customer_name} | Công nợ hiện tại: {format_money(detail.current_balance or 0)}"
        )
        self._customer_label.setProperty("class", "muted")

        self._items_table = SourceInvoiceItemsTable()
        self._items_table.load_items(list(detail.items), initial_quantities=detail.selected_quantities)
        self._items_table.totals_changed.connect(self._refresh_total)

        self._summary_widget = ReturnSummaryWidget(self)
        self._summary_widget.set_walk_in_mode(detail.customer_id is None)
        self._summary_widget.mode_combo.setCurrentIndex(0 if detail.handling_mode.value == "REFUND_NOW" else 1)
        self._summary_widget.note_input.setText(detail.note or "")
        self._refresh_total()

        save_button = QPushButton("Lưu thay đổi")
        save_button.clicked.connect(self._save)

        layout = QVBoxLayout(self)
        layout.addWidget(self._header_label)
        layout.addWidget(self._customer_label)
        layout.addWidget(self._items_table)
        layout.addWidget(self._summary_widget)
        layout.addWidget(save_button)

    def _refresh_total(self) -> None:
        self._summary_widget.set_total(self._items_table.total_amount())

    def _save(self) -> None:
        try:
            items = self._items_table.selected_return_items()
            if not items:
                raise ValidationError("Phải nhập ít nhất 1 dòng trả hàng > 0.")
            if self._detail.customer_id is None and self._summary_widget.selected_mode().value != "REFUND_NOW":
                raise ValidationError("Khách lẻ chỉ được phép hoàn tiền ngay.")
            self._controller.update_return_invoice(
                self._detail.return_invoice_id,
                items=items,
                handling_mode=self._summary_widget.selected_mode().value,
                note=self._summary_widget.note_input.text() or None,
            )
            self.accept()
        except Exception as exc:
            MessageBox.error(self, "Không cập nhật được phiếu trả hàng", str(exc))
