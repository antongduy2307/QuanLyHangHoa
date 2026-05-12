from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget

from core.config import Settings
from modules.attendance.product_sync_service import ProductCutWorkItem
from shell.app_window import AppWindow


class _FakeSyncResult:
    def __init__(self, incomplete_items: list[ProductCutWorkItem] | None = None, warnings: list[str] | None = None) -> None:
        self.incomplete_items = incomplete_items or []
        self.warnings = warnings or []


class _FakeSyncService:
    def __init__(self, results: list[_FakeSyncResult] | None = None, *, raise_error: bool = False) -> None:
        self.results = results or [_FakeSyncResult()]
        self.raise_error = raise_error
        self.calls = 0

    def sync_products_to_cut_work(self) -> _FakeSyncResult:
        self.calls += 1
        if self.raise_error:
            raise RuntimeError("sync failed")
        index = min(self.calls - 1, len(self.results) - 1)
        return self.results[index]


class _FakeSettingsPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.open_calls: list[int | None] = []

    def open_attendance_price_settings(self, first_incomplete_id: int | None = None) -> None:
        self.open_calls.append(first_incomplete_id)


class AppWindowAttendanceSyncTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temp_root = Path(tempfile.mkdtemp(prefix="app-window-attendance-sync-"))
        self.settings = Settings(
            app_name="QuanLyHangHoaTest",
            app_data_dir=self._temp_root / "appdata",
            db_path=self._temp_root / "appdata" / "app.db",
            log_dir=self._temp_root / "appdata" / "logs",
            export_dir=self._temp_root / "appdata" / "exports",
            backup_dir=self._temp_root / "appdata" / "backups",
            temp_dir=self._temp_root / "appdata" / "temp",
            log_level="INFO",
            update_manifest_url="https://example.com/version.json",
            update_check_timeout_ms=1000,
            update_download_timeout_ms=1000,
            update_download_retry_count=1,
            update_startup_delay_ms=60_000,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self._temp_root, ignore_errors=True)

    def _build_window(self, sync_service: _FakeSyncService) -> tuple[AppWindow, QWidget, _FakeSettingsPage, QTabWidget]:
        attendance_page = QWidget()
        settings_page = _FakeSettingsPage()
        modules = (
            SimpleNamespace(key="inventory", label="Hàng hóa", page_factory=QWidget),
            SimpleNamespace(key="attendance", label="Chấm công", page_factory=lambda: attendance_page),
            SimpleNamespace(key="settings", label="Cài đặt", page_factory=lambda: settings_page),
        )
        window = AppWindow("Test", modules, self.settings)
        window._attendance_product_sync_service = sync_service
        tabs = window.findChild(QTabWidget)
        assert tabs is not None
        return window, attendance_page, settings_page, tabs

    def _incomplete_item(self, item_id: int = 100, name: str = "Bao thiếu") -> ProductCutWorkItem:
        return ProductCutWorkItem(
            id=item_id,
            name=name,
            source_product_id=10,
            quota_quantity=0,
            excess_unit_price=0,
            is_excluded_from_attendance=False,
        )

    def test_entering_attendance_tab_runs_product_sync(self) -> None:
        sync_service = _FakeSyncService()
        window, attendance_page, _settings_page, tabs = self._build_window(sync_service)
        try:
            tabs.setCurrentWidget(attendance_page)
            self.assertEqual(sync_service.calls, 1)
        finally:
            window.close()

    def test_incomplete_linked_row_shows_popup(self) -> None:
        sync_service = _FakeSyncService([_FakeSyncResult([self._incomplete_item()])])
        window, attendance_page, _settings_page, tabs = self._build_window(sync_service)
        popup_calls: list[list[ProductCutWorkItem]] = []
        window._show_incomplete_cut_work_warning = lambda items: popup_calls.append(items) or False  # type: ignore[method-assign]
        try:
            tabs.setCurrentWidget(attendance_page)
            self.assertEqual(len(popup_calls), 1)
            self.assertEqual(popup_calls[0][0].name, "Bao thiếu")
        finally:
            window.close()

    def test_configured_linked_row_does_not_show_popup(self) -> None:
        sync_service = _FakeSyncService([_FakeSyncResult([])])
        window, attendance_page, _settings_page, tabs = self._build_window(sync_service)
        popup_calls: list[list[ProductCutWorkItem]] = []
        window._show_incomplete_cut_work_warning = lambda items: popup_calls.append(items) or False  # type: ignore[method-assign]
        try:
            tabs.setCurrentWidget(attendance_page)
            self.assertEqual(popup_calls, [])
        finally:
            window.close()

    def test_excluded_linked_row_does_not_show_popup(self) -> None:
        sync_service = _FakeSyncService([_FakeSyncResult([])])
        window, attendance_page, _settings_page, tabs = self._build_window(sync_service)
        popup_calls: list[list[ProductCutWorkItem]] = []
        window._show_incomplete_cut_work_warning = lambda items: popup_calls.append(items) or False  # type: ignore[method-assign]
        try:
            tabs.setCurrentWidget(attendance_page)
            self.assertEqual(popup_calls, [])
        finally:
            window.close()

    def test_popup_later_stays_on_attendance_tab(self) -> None:
        sync_service = _FakeSyncService([_FakeSyncResult([self._incomplete_item()])])
        window, attendance_page, _settings_page, tabs = self._build_window(sync_service)
        window._show_incomplete_cut_work_warning = lambda _items: False  # type: ignore[method-assign]
        try:
            tabs.setCurrentWidget(attendance_page)
            self.assertIs(tabs.currentWidget(), attendance_page)
        finally:
            window.close()

    def test_popup_go_to_settings_switches_to_settings_and_focuses_incomplete_row(self) -> None:
        item = self._incomplete_item(item_id=321)
        sync_service = _FakeSyncService([_FakeSyncResult([item])])
        window, attendance_page, settings_page, tabs = self._build_window(sync_service)
        window._show_incomplete_cut_work_warning = lambda _items: True  # type: ignore[method-assign]
        try:
            tabs.setCurrentWidget(attendance_page)
            self.assertIs(tabs.currentWidget(), settings_page)
            self.assertEqual(settings_page.open_calls, [321])
        finally:
            window.close()

    def test_popup_does_not_repeat_while_already_in_attendance_tab(self) -> None:
        sync_service = _FakeSyncService([_FakeSyncResult([self._incomplete_item()])])
        window, attendance_page, _settings_page, tabs = self._build_window(sync_service)
        popup_calls: list[list[ProductCutWorkItem]] = []
        window._show_incomplete_cut_work_warning = lambda items: popup_calls.append(items) or False  # type: ignore[method-assign]
        try:
            tabs.setCurrentWidget(attendance_page)
            attendance_index = tabs.indexOf(attendance_page)
            window._handle_main_tab_changed(attendance_index)
            self.assertEqual(len(popup_calls), 1)
            self.assertEqual(sync_service.calls, 1)
        finally:
            window.close()

    def test_leaving_and_reentering_attendance_can_show_popup_again(self) -> None:
        sync_service = _FakeSyncService(
            [
                _FakeSyncResult([self._incomplete_item(1, "Bao thiếu 1")]),
                _FakeSyncResult([self._incomplete_item(2, "Bao thiếu 2")]),
            ]
        )
        window, attendance_page, _settings_page, tabs = self._build_window(sync_service)
        popup_calls: list[list[ProductCutWorkItem]] = []
        window._show_incomplete_cut_work_warning = lambda items: popup_calls.append(items) or False  # type: ignore[method-assign]
        try:
            tabs.setCurrentWidget(attendance_page)
            tabs.setCurrentIndex(0)
            tabs.setCurrentWidget(attendance_page)
            self.assertEqual(len(popup_calls), 2)
            self.assertEqual(sync_service.calls, 2)
        finally:
            window.close()

    def test_sync_failure_does_not_block_attendance_tab(self) -> None:
        sync_service = _FakeSyncService(raise_error=True)
        window, attendance_page, _settings_page, tabs = self._build_window(sync_service)
        popup_calls: list[list[ProductCutWorkItem]] = []
        window._show_incomplete_cut_work_warning = lambda items: popup_calls.append(items) or False  # type: ignore[method-assign]
        try:
            tabs.setCurrentWidget(attendance_page)
            self.assertIs(tabs.currentWidget(), attendance_page)
            self.assertEqual(sync_service.calls, 1)
            self.assertEqual(popup_calls, [])
        finally:
            window.close()


if __name__ == "__main__":
    unittest.main()
