from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import shutil
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PyQt6.QtCore import QDate, pyqtSignal
from PyQt6.QtWidgets import QApplication, QWidget

from core.config import Settings
from modules.reporting.dto import DateRangePresetDTO, RevenueTimeseriesPointDTO, SalesSummaryDTO, TopProductReportRowDTO
from modules.reporting.ui.report_page import ReportPage
from shell.app_window import AppWindow


class _FakeReportingController:
    def __init__(self) -> None:
        self.resolve_calls: list[tuple[str, datetime | None, datetime | None]] = []
        self.top_product_calls: list[tuple[datetime, datetime, str, int]] = []
        self.timeseries_calls: list[tuple[date, date]] = []
        self.summary_calls: list[tuple[datetime, datetime]] = []

    def resolve_range(
        self,
        preset: str,
        *,
        custom_start: datetime | None = None,
        custom_end: datetime | None = None,
    ) -> DateRangePresetDTO:
        self.resolve_calls.append((preset, custom_start, custom_end))
        return DateRangePresetDTO(
            start_datetime=custom_start or datetime(2026, 4, 1, 0, 0, 0),
            end_datetime=custom_end or datetime(2026, 4, 30, 23, 59, 59),
        )

    def load_summary(self, start_datetime: datetime, end_datetime: datetime) -> SalesSummaryDTO:
        self.summary_calls.append((start_datetime, end_datetime))
        return SalesSummaryDTO(
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            gross_sales_amount=Decimal("1000"),
            return_amount=Decimal("100"),
            net_revenue=Decimal("900"),
            invoice_count=2,
            return_count=1,
        )

    def load_top_products(
        self,
        start_datetime: datetime,
        end_datetime: datetime,
        *,
        sort_by: str,
        limit: int,
    ) -> list[TopProductReportRowDTO]:
        self.top_product_calls.append((start_datetime, end_datetime, sort_by, limit))
        return [
            TopProductReportRowDTO(
                product_id=1,
                product_code="P001",
                product_name="Hang 1",
                unit_type="BAO",
                sold_quantity=Decimal("10"),
                gross_revenue=Decimal("1000"),
                returned_quantity=Decimal("1"),
                return_amount=Decimal("100"),
                net_quantity=Decimal("9"),
                net_revenue=Decimal("900"),
            )
        ]

    def load_timeseries(self, start_date: date, end_date: date) -> list[RevenueTimeseriesPointDTO]:
        self.timeseries_calls.append((start_date, end_date))
        return [
            RevenueTimeseriesPointDTO(
                bucket_date=start_date,
                gross_sales_amount=Decimal("1000"),
                return_amount=Decimal("100"),
                net_revenue=Decimal("900"),
            )
        ]


class _FakeTransactionPage(QWidget):
    transaction_changed = pyqtSignal()


class _FakeReportingPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.notify_calls = 0

    def notify_data_changed(self) -> None:
        self.notify_calls += 1


class _FakeHistoryPage(QWidget):
    history_changed = pyqtSignal()


class ReportingRefreshTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp_dir = Path(tempfile.mkdtemp(prefix="report-refresh-"))

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp_dir, ignore_errors=True)

    def test_report_page_refresh_uses_current_state_and_defers_when_hidden(self) -> None:
        controller = _FakeReportingController()
        page = ReportPage(controller)
        page.show()
        self._app.processEvents()

        controller.resolve_calls.clear()
        controller.summary_calls.clear()
        controller.top_product_calls.clear()
        controller.timeseries_calls.clear()

        page._range_selector.preset_combo.setCurrentIndex(page._range_selector.preset_combo.findData("custom"))
        page._range_selector.start_date_edit.setDate(QDate(2026, 4, 1))
        page._range_selector.end_date_edit.setDate(QDate(2026, 4, 15))
        page._top_products_widget.sort_by_combo.setCurrentIndex(page._top_products_widget.sort_by_combo.findData("quantity"))
        page._top_products_widget.limit_input.setValue(7)

        page.notify_data_changed()
        self._app.processEvents()

        self.assertEqual(controller.resolve_calls[-1][0], "custom")
        self.assertEqual(controller.resolve_calls[-1][1], datetime(2026, 4, 1, 0, 0, 0))
        self.assertEqual(controller.resolve_calls[-1][2], datetime(2026, 4, 15, 23, 59, 59, 999999))
        self.assertEqual(controller.top_product_calls[-1][2:], ("quantity", 7))
        self.assertEqual(controller.timeseries_calls[-1], (date(2026, 4, 1), date(2026, 4, 15)))

        visible_call_count = len(controller.summary_calls)
        page.hide()
        self._app.processEvents()
        page.notify_data_changed()
        self._app.processEvents()
        self.assertEqual(len(controller.summary_calls), visible_call_count)

        page.show()
        self._app.processEvents()
        self.assertEqual(len(controller.summary_calls), visible_call_count + 1)
        page.deleteLater()

    def test_app_window_forwards_transaction_and_history_changes_to_reporting_page(self) -> None:
        sales_page = _FakeTransactionPage()
        customer_page = _FakeTransactionPage()
        reporting_page = _FakeReportingPage()

        settings = Settings(
            app_name="QuanLyHangHoaTest",
            app_data_dir=self._tmp_dir / "appdata",
            db_path=self._tmp_dir / "appdata" / "app.db",
            log_dir=self._tmp_dir / "appdata" / "logs",
            export_dir=self._tmp_dir / "appdata" / "exports",
            backup_dir=self._tmp_dir / "appdata" / "backups",
            temp_dir=self._tmp_dir / "appdata" / "temp",
            log_level="INFO",
            update_manifest_url="https://example.com/version.json",
            update_check_timeout_ms=1000,
            update_download_timeout_ms=1000,
            update_download_retry_count=1,
            update_startup_delay_ms=60_000,
        )

        modules = (
            SimpleNamespace(key="sales", label="Sales", page_factory=lambda: sales_page),
            SimpleNamespace(key="customer", label="Customer", page_factory=lambda: customer_page),
            SimpleNamespace(key="reporting", label="Reporting", page_factory=lambda: reporting_page),
        )

        with patch("shell.app_window.HistoryPage", _FakeHistoryPage):
            window = AppWindow("Test", modules, settings)
        try:
            sales_page.transaction_changed.emit()
            customer_page.transaction_changed.emit()
            window._history_page.history_changed.emit()  # type: ignore[union-attr]
            self._app.processEvents()

            self.assertEqual(reporting_page.notify_calls, 3)
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
