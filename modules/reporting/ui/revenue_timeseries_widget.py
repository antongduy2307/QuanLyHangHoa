from __future__ import annotations

from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget

from modules.reporting.dto import RevenueTimeseriesPointDTO
from shared.formatting.money import format_money
from shared.widgets.table_helpers import configure_table_widget


class RevenueTimeseriesWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Ngay", "Gross", "Return", "Net"])
        configure_table_widget(self.table)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)

    def set_points(self, points: list[RevenueTimeseriesPointDTO]) -> None:
        self.table.setRowCount(len(points))
        for row_index, point in enumerate(points):
            self.table.setItem(row_index, 0, QTableWidgetItem(point.bucket_date.isoformat()))
            self.table.setItem(row_index, 1, QTableWidgetItem(format_money(point.gross_sales_amount)))
            self.table.setItem(row_index, 2, QTableWidgetItem(format_money(point.return_amount)))
            self.table.setItem(row_index, 3, QTableWidgetItem(format_money(point.net_revenue)))
