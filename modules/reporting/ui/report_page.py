from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from modules.reporting.controller import ReportingController
from modules.reporting.ui.date_range_selector_widget import DateRangeSelectorWidget
from modules.reporting.ui.revenue_timeseries_widget import RevenueTimeseriesWidget
from modules.reporting.ui.sales_summary_widget import SalesSummaryWidget
from modules.reporting.ui.top_products_table_widget import TopProductsTableWidget


class ReportPage(QWidget):
    def __init__(self, controller: ReportingController) -> None:
        super().__init__()
        self._controller = controller
        self._range_selector = DateRangeSelectorWidget(self)
        self._summary_widget = SalesSummaryWidget(self)
        self._timeseries_widget = RevenueTimeseriesWidget(self)
        self._top_products_widget = TopProductsTableWidget(self)

        layout = QVBoxLayout(self)
        layout.addWidget(self._range_selector)
        layout.addWidget(self._summary_widget)
        layout.addWidget(self._timeseries_widget)
        layout.addWidget(self._top_products_widget)

        self._range_selector.load_requested.connect(self._load_report)
        self._load_report("last_7_days", None, None)

    def _load_report(self, preset: str, custom_start: object, custom_end: object) -> None:
        try:
            resolved = self._controller.resolve_range(
                preset,
                custom_start=custom_start,
                custom_end=custom_end,
            )
            summary = self._controller.load_summary(resolved.start_datetime, resolved.end_datetime)
            top_products = self._controller.load_top_products(
                resolved.start_datetime,
                resolved.end_datetime,
                sort_by=self._top_products_widget.current_sort_by(),
                limit=self._top_products_widget.current_limit(),
            )
            timeseries = self._controller.load_timeseries(
                resolved.start_datetime.date(),
                resolved.end_datetime.date(),
            )
            self._summary_widget.set_summary(summary)
            self._top_products_widget.set_rows(top_products)
            self._timeseries_widget.set_points(timeseries)
        except Exception as exc:
            QMessageBox.critical(self, "Lỗi báo cáo", str(exc))
