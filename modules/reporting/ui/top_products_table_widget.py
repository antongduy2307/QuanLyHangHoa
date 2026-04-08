from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from modules.reporting.dto import TopProductReportRowDTO
from shared.formatting.money import format_money
from shared.widgets.numeric_inputs import SelectAllSpinBox
from shared.widgets.table_helpers import configure_table_widget


class TopProductsTableWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.sort_by_combo = QComboBox()
        self.sort_by_combo.addItem("Revenue", "revenue")
        self.sort_by_combo.addItem("Quantity", "quantity")
        self.limit_input = SelectAllSpinBox()
        self.limit_input.setRange(1, 100)
        self.limit_input.setValue(10)

        self.table = QTableWidget(0, 9)
        self.table.setHorizontalHeaderLabels([
            "Mã hàng",
            "Tên hàng",
            "Đơn vị",
            "Đã bán",
            "Doanh thu gộp",
            "Đã trả",
            "Tiền trả",
            "Số lượng ròng",
            "Doanh thu ròng",
        ])
        configure_table_widget(self.table)

        control_layout = QHBoxLayout()
        control_layout.addWidget(QLabel("Sắp xếp theo"))
        control_layout.addWidget(self.sort_by_combo)
        control_layout.addWidget(QLabel("Giới hạn"))
        control_layout.addWidget(self.limit_input)
        control_layout.addStretch()

        layout = QVBoxLayout(self)
        layout.addLayout(control_layout)
        layout.addWidget(self.table)

    def current_sort_by(self) -> str:
        return str(self.sort_by_combo.currentData())

    def current_limit(self) -> int:
        return int(self.limit_input.value())

    def set_rows(self, rows: list[TopProductReportRowDTO]) -> None:
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            self.table.setItem(row_index, 0, QTableWidgetItem(row.product_code))
            self.table.setItem(row_index, 1, QTableWidgetItem(row.product_name))
            self.table.setItem(row_index, 2, QTableWidgetItem(row.unit_type))
            self.table.setItem(row_index, 3, QTableWidgetItem(str(row.sold_quantity)))
            self.table.setItem(row_index, 4, QTableWidgetItem(format_money(row.gross_revenue)))
            self.table.setItem(row_index, 5, QTableWidgetItem(str(row.returned_quantity)))
            self.table.setItem(row_index, 6, QTableWidgetItem(format_money(row.return_amount)))
            self.table.setItem(row_index, 7, QTableWidgetItem(str(row.net_quantity)))
            self.table.setItem(row_index, 8, QTableWidgetItem(format_money(row.net_revenue)))
