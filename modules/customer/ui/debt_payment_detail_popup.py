from __future__ import annotations

from typing import Callable

from PyQt6.QtWidgets import QDialog, QGridLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from modules.customer.models import CustomerBalanceLedger
from shared.formatting.dates import format_datetime
from shared.formatting.money import format_money
from shared.widgets.ui_scale import apply_large_ui, boost_font_size


class DebtPaymentDetailPopup(QDialog):
    def __init__(
        self,
        ledger: CustomerBalanceLedger,
        parent: QDialog | None = None,
        *,
        controller=None,
        on_updated: Callable[[], None] | None = None,
        on_open_record: Callable[[], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self._ledger = ledger
        self._controller = controller
        self._on_updated = on_updated
        self._on_open_record = on_open_record

        self.setWindowTitle(f"Trả nợ {ledger.ref_id}")
        self.resize(760, 420)
        self.setMinimumSize(680, 360)
        self.setObjectName("debtDetailPopup")

        header_widget = self._build_header()

        self._open_record_button = QPushButton("Mở phiếu")
        self._open_record_button.clicked.connect(self._open_record)
        self._open_record_button.setVisible(self._on_open_record is not None)
        self._open_record_button.setObjectName("recordOpenButton")

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.addWidget(header_widget)
        if self._on_open_record is not None:
            button_row = QGridLayout()
            button_row.setContentsMargins(0, 0, 0, 0)
            button_row.addWidget(self._open_record_button, 0, 2)
            button_row.setColumnStretch(0, 1)
            button_row.setColumnStretch(1, 0)
            button_row.setColumnStretch(2, 0)
            layout.addLayout(button_row)

        apply_large_ui(self)
        self.setStyleSheet(
            self.styleSheet()
            + f"""
QDialog#debtDetailPopup {{
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
"""
        )

    def _build_header(self) -> QWidget:
        customer_name = self._ledger.customer.customer_name if self._ledger.customer else "-"
        phone = self._ledger.customer.phone if self._ledger.customer and self._ledger.customer.phone else "-"

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)

        left_title = QLabel("Thông tin phiếu")
        left_title.setObjectName("detailTitle")
        middle_title = QLabel("Ảnh hưởng giao dịch")
        middle_title.setObjectName("detailTitle")
        right_title = QLabel("Ghi chú")
        right_title.setObjectName("detailTitle")

        note_label = QLabel(self._ledger.note or "-")
        note_label.setWordWrap(True)
        note_label.setObjectName("detailNote")

        left_col = QVBoxLayout()
        left_col.setSpacing(4)
        left_col.addWidget(left_title)
        left_col.addWidget(QLabel(f"Loại giao dịch: Trả nợ"))
        left_col.addWidget(QLabel(f"Thời gian: {format_datetime(self._ledger.effective_transaction_datetime)}"))
        left_col.addWidget(QLabel(f"Khách hàng: {customer_name}"))

        middle_col = QVBoxLayout()
        middle_col.setSpacing(4)
        middle_col.addWidget(middle_title)
        middle_col.addWidget(QLabel(f"Số tiền trả nợ: {format_money(abs(self._ledger.amount_delta))}"))
        middle_col.addWidget(QLabel(f"Số điện thoại: {phone}"))
        middle_col.addWidget(QLabel(f"Dư nợ sau giao dịch: {format_money(self._ledger.balance_after)}"))

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
