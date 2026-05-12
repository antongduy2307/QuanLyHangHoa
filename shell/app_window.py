from __future__ import annotations

from collections.abc import Sequence
import os

from PyQt6.QtCore import QCoreApplication, QTimer, Qt
from PyQt6.QtWidgets import QApplication, QMainWindow, QMessageBox, QProgressDialog

from core.config import Settings
from core.logging import get_logger
from modules.attendance.product_sync_service import AttendanceProductSyncService, ProductCutWorkItem
from modules.diagnostics.service import DiagnosticsService
from modules.settings.backup_service import UserBackupService
from modules.settings.service import get_ui_scale_preset
from modules.update.service import UpdateCheckResult, UpdateDownloadResult, UpdateService
from modules.update.ui.update_dialog import UpdateDialog
from shared.widgets.message_box import MessageBox
from shared.widgets.ui_scale import apply_large_ui
from shell.history_page import HistoryPage
from shell.navigation import NavigationTabs


LOGGER = get_logger(__name__)


class AppWindow(QMainWindow):
    def __init__(self, title: str, modules: Sequence[object], settings: Settings) -> None:
        super().__init__()
        app = QApplication.instance()
        if app is None:
            raise RuntimeError("QApplication must be initialized before AppWindow.")

        self._settings = settings
        self._diagnostics_service = DiagnosticsService(settings, app)
        self._backup_service = UserBackupService(settings)
        self.setWindowTitle(title)
        self.resize(1200, 720)
        self._module_pages: dict[str, object] = {}
        self._history_page: HistoryPage | None = None
        self._attendance_page: object | None = None
        self._reporting_page: object | None = None
        self._settings_page: object | None = None
        self._current_main_tab_key: str | None = None
        self._active_check_origin: str | None = None
        self._pending_update_result: UpdateCheckResult | None = None
        self._update_progress_dialog: QProgressDialog | None = None
        self._update_service = UpdateService(settings=settings, parent=self)
        self._attendance_product_sync_service = AttendanceProductSyncService()
        self._update_service.check_finished.connect(self._handle_update_check_result)
        self._update_service.download_finished.connect(self._handle_update_download_result)
        self._update_service.download_progress.connect(self._handle_update_download_progress)

        initial_ui_scale_preset = get_ui_scale_preset()

        tabs = NavigationTabs()
        self._navigation_tabs = tabs
        history_inserted = False
        for module_spec in modules:
            if module_spec.key in {"attendance", "settings"} and not history_inserted:
                self._history_page = HistoryPage()
                tabs.add_page("Lịch sử", self._history_page)
                self._apply_ui_scale_to_page(self._history_page, initial_ui_scale_preset)
                history_inserted = True
            page = module_spec.page_factory()
            self._module_pages[module_spec.key] = page
            if module_spec.key == "attendance":
                self._attendance_page = page
            if module_spec.key == "reporting":
                self._reporting_page = page
            if module_spec.key == "settings":
                self._settings_page = page
                if hasattr(page, "check_updates_requested"):
                    page.check_updates_requested.connect(self._run_manual_update_check)
                if hasattr(page, "backup_requested"):
                    page.backup_requested.connect(self._create_user_backup)
                if hasattr(page, "open_logs_requested"):
                    page.open_logs_requested.connect(self._open_logs_directory)
                if hasattr(page, "export_diagnostics_requested"):
                    page.export_diagnostics_requested.connect(self._export_diagnostics)
                if hasattr(page, "attendance_config_changed"):
                    page.attendance_config_changed.connect(self._refresh_attendance_page)
                if hasattr(page, "set_update_status"):
                    page.set_update_status("Sẵn sàng kiểm tra cập nhật.")
            tabs.add_page(module_spec.label, page)
            self._apply_ui_scale_to_page(page, initial_ui_scale_preset)
            if hasattr(page, "ui_scale_changed"):
                page.ui_scale_changed.connect(self._apply_ui_scale_preset_to_pages)

        if not history_inserted:
            self._history_page = HistoryPage()
            tabs.add_page("Lịch sử", self._history_page)
            self._apply_ui_scale_to_page(self._history_page, initial_ui_scale_preset)
        self.setCentralWidget(tabs)
        self._current_main_tab_key = self._module_key_for_widget(tabs.currentWidget())
        tabs.currentChanged.connect(self._handle_main_tab_changed)

        self._wire_report_refresh_sources()

        self._startup_update_timer = QTimer(self)
        self._startup_update_timer.setSingleShot(True)
        self._startup_update_timer.timeout.connect(self._run_startup_update_check)
        self._startup_update_timer.start(settings.update_startup_delay_ms)

    def navigate_to_history_transaction(self, transaction_kind: str, transaction_id: int) -> None:
        if self._history_page is None:
            return
        history_index = self._navigation_tabs.indexOf(self._history_page)
        if history_index >= 0:
            self._navigation_tabs.setCurrentIndex(history_index)
        self._history_page.open_transaction_detail(transaction_kind, transaction_id)

    def open_sales_invoice_editor(self, invoice_id: int) -> None:
        sales_page = self._module_pages.get("sales")
        if sales_page is None or not hasattr(sales_page, "open_invoice_edit_tab"):
            return
        sales_index = self._navigation_tabs.indexOf(sales_page)
        if sales_index >= 0:
            self._navigation_tabs.setCurrentIndex(sales_index)
        sales_page.open_invoice_edit_tab(invoice_id)

    def open_sales_return_editor(self, return_id: int) -> None:
        sales_page = self._module_pages.get("sales")
        if sales_page is None or not hasattr(sales_page, "open_return_edit_tab"):
            return
        sales_index = self._navigation_tabs.indexOf(sales_page)
        if sales_index >= 0:
            self._navigation_tabs.setCurrentIndex(sales_index)
        sales_page.open_return_edit_tab(return_id)

    def open_order_sales_draft(self, order_id: int) -> None:
        sales_page = self._module_pages.get("sales")
        if sales_page is None or not hasattr(sales_page, "open_order_sales_draft"):
            return
        sales_index = self._navigation_tabs.indexOf(sales_page)
        if sales_index >= 0:
            self._navigation_tabs.setCurrentIndex(sales_index)
        sales_page.open_order_sales_draft(order_id)

    def open_order_editor(self, order_id: int) -> None:
        sales_page = self._module_pages.get("sales")
        if sales_page is None or not hasattr(sales_page, "open_order_edit_tab"):
            return
        sales_index = self._navigation_tabs.indexOf(sales_page)
        if sales_index >= 0:
            self._navigation_tabs.setCurrentIndex(sales_index)
        sales_page.open_order_edit_tab(order_id)

    def _wire_report_refresh_sources(self) -> None:
        if self._reporting_page is None or not hasattr(self._reporting_page, "notify_data_changed"):
            return

        for module_key, page in self._module_pages.items():
            if module_key == "reporting":
                continue
            if hasattr(page, "transaction_changed"):
                page.transaction_changed.connect(self._handle_data_changed_from_pages)
            if hasattr(page, "order_changed"):
                page.order_changed.connect(self._handle_data_changed_from_pages)
        if self._history_page is not None:
            self._history_page.history_changed.connect(self._notify_reporting_page_dirty)

    def _notify_reporting_page_dirty(self) -> None:
        if self._reporting_page is not None and hasattr(self._reporting_page, "notify_data_changed"):
            self._reporting_page.notify_data_changed()

    def _refresh_attendance_page(self) -> None:
        if self._attendance_page is not None and hasattr(self._attendance_page, "refresh_all"):
            self._attendance_page.refresh_all()

    def _module_key_for_widget(self, widget: object | None) -> str | None:
        for module_key, page in self._module_pages.items():
            if page is widget:
                return module_key
        if self._history_page is widget:
            return "history"
        return None

    def _handle_main_tab_changed(self, index: int) -> None:
        widget = self._navigation_tabs.widget(index)
        next_key = self._module_key_for_widget(widget)
        previous_key = self._current_main_tab_key
        if next_key == previous_key:
            return
        self._current_main_tab_key = next_key
        if next_key == "attendance" and previous_key != "attendance":
            self._handle_enter_attendance_tab()

    def _handle_enter_attendance_tab(self) -> None:
        try:
            sync_result = self._attendance_product_sync_service.sync_products_to_cut_work()
        except Exception as exc:
            LOGGER.warning("Attendance product sync failed on Attendance tab entry: %s", exc)
            return
        for warning in sync_result.warnings:
            LOGGER.warning("Attendance product sync warning on Attendance tab entry: %s", warning)
        incomplete_items = sync_result.incomplete_items
        if not incomplete_items:
            return
        if self._show_incomplete_cut_work_warning(incomplete_items):
            self._open_attendance_price_settings(incomplete_items[0].id)

    def _show_incomplete_cut_work_warning(self, incomplete_items: list[ProductCutWorkItem]) -> bool:
        preview_names = "\n".join(f"- {item.name}" for item in incomplete_items[:5])
        if len(incomplete_items) > 5:
            preview_names = f"{preview_names}\n- ..."
        message = (
            f"Có {len(incomplete_items)} mặt hàng đã được đồng bộ sang việc cắt nhưng chưa cấu hình đủ "
            "số lượng khoán hoặc đơn giá vượt khoán.\n\n"
            "Vui lòng vào Cài đặt giá chấm công để nhập đủ thông tin, hoặc tick "
            '"Không dùng cho chấm công" nếu mặt hàng này không dùng để chấm công.\n\n'
            f"Một số mục cần kiểm tra:\n{preview_names}"
        )
        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setWindowTitle("Thiếu cấu hình việc cắt")
        dialog.setText(message)
        settings_button = dialog.addButton("Đi tới cài đặt", QMessageBox.ButtonRole.AcceptRole)
        dialog.addButton("Để sau", QMessageBox.ButtonRole.RejectRole)
        dialog.exec()
        return dialog.clickedButton() is settings_button

    def _open_attendance_price_settings(self, first_incomplete_id: int | None = None) -> None:
        if self._settings_page is None:
            return
        settings_index = self._navigation_tabs.indexOf(self._settings_page)
        if settings_index >= 0:
            self._navigation_tabs.setCurrentIndex(settings_index)
        if hasattr(self._settings_page, "open_attendance_price_settings"):
            self._settings_page.open_attendance_price_settings(first_incomplete_id)

    def _handle_data_changed_from_pages(self) -> None:
        if self._history_page is not None and hasattr(self._history_page, "reload_all_views"):
            self._history_page.reload_all_views()
        customer_page = self._module_pages.get("customer")
        if customer_page is not None and hasattr(customer_page, "_customer_list_view") and hasattr(customer_page._customer_list_view, "reload"):
            customer_page._customer_list_view.reload()
        inventory_page = self._module_pages.get("inventory")
        if inventory_page is not None:
            from modules.inventory.ui.product_list_view import ProductListView

            product_list_view = inventory_page.findChild(ProductListView)
            if product_list_view is not None and hasattr(product_list_view, "reload"):
                product_list_view.reload()
        orders_page = self._module_pages.get("orders")
        if orders_page is not None and hasattr(orders_page, "reload"):
            orders_page.reload()
        self._notify_reporting_page_dirty()

    def _apply_ui_scale_preset_to_pages(self, preset: str) -> None:
        for page in self._module_pages.values():
            self._apply_ui_scale_to_page(page, preset)
        if self._history_page is not None:
            self._apply_ui_scale_to_page(self._history_page, preset)

    def _apply_ui_scale_to_page(self, page: object, preset: str) -> None:
        if hasattr(page, "apply_ui_scale_preset"):
            page.apply_ui_scale_preset(preset)
        apply_large_ui(page, preset)

    def _run_manual_update_check(self) -> None:
        self._start_update_check("manual")

    def _run_startup_update_check(self) -> None:
        self._start_update_check("startup")

    def _start_update_check(self, origin: str) -> None:
        if self._active_check_origin is not None or self._update_progress_dialog is not None:
            if origin == "manual":
                MessageBox.info(self, "Cập nhật ứng dụng", "Đang có một tác vụ cập nhật khác chạy.")
            return

        self._active_check_origin = origin
        self._set_update_busy(True, "Đang kiểm tra cập nhật...")
        self._update_service.check_for_update()

    def _handle_update_check_result(self, result: UpdateCheckResult) -> None:
        origin = self._active_check_origin or "manual"
        self._active_check_origin = None

        if result.error:
            LOGGER.warning(
                "Update check failed | origin=%s | manifest_url=%s | error=%s | app_continues=True",
                origin,
                result.manifest_url,
                result.error,
            )
            self._set_update_busy(False, "Không kiểm tra được cập nhật. Ứng dụng vẫn hoạt động bình thường.")
            if origin == "manual":
                MessageBox.warning(
                    self,
                    "Cập nhật ứng dụng",
                    f"{result.error}\n\nĐây không phải lỗi khởi động hay lỗi dữ liệu. Bạn vẫn có thể tiếp tục sử dụng ứng dụng.",
                )
            return

        if result.has_update or result.is_forced_update:
            self._set_update_busy(False, f"Đã tìm thấy phiên bản {result.latest_version}.")
            self._present_update_dialog(result)
            return

        self._set_update_busy(False, "Bạn đang dùng phiên bản mới nhất.")
        if origin == "manual":
            MessageBox.info(self, "Cập nhật ứng dụng", "Bạn đang dùng phiên bản mới nhất.")

    def _present_update_dialog(self, result: UpdateCheckResult) -> None:
        dialog = UpdateDialog(result, self)
        dialog.exec()

        if dialog.selected_action == "update":
            self._begin_update_download(result)
            return
        if dialog.selected_action == "exit":
            app = QCoreApplication.instance()
            if app is not None:
                app.quit()

    def _begin_update_download(self, result: UpdateCheckResult) -> None:
        if not result.latest_version or not result.installer_url:
            MessageBox.warning(self, "Cập nhật ứng dụng", "Manifest cập nhật không có installer hợp lệ.")
            return

        self._pending_update_result = result
        self._set_update_busy(True, f"Đang tải phiên bản {result.latest_version}...")

        progress_dialog = QProgressDialog("Đang tải installer cập nhật...", None, 0, 0, self)
        progress_dialog.setWindowTitle("Cập nhật ứng dụng")
        progress_dialog.setWindowModality(Qt.WindowModality.WindowModal)
        progress_dialog.setCancelButton(None)
        progress_dialog.setMinimumDuration(0)
        progress_dialog.show()
        self._update_progress_dialog = progress_dialog

        self._update_service.download_installer(result.installer_url, result.latest_version)

    def _handle_update_download_progress(self, received: int, total: int) -> None:
        if self._update_progress_dialog is None:
            return

        if total > 0:
            self._update_progress_dialog.setRange(0, total)
            self._update_progress_dialog.setValue(received)
            self._update_progress_dialog.setLabelText(f"Đang tải installer cập nhật... {received}/{total} bytes")
            return

        self._update_progress_dialog.setRange(0, 0)

    def _handle_update_download_result(self, result: UpdateDownloadResult) -> None:
        pending_result = self._pending_update_result
        self._pending_update_result = None

        if self._update_progress_dialog is not None:
            self._update_progress_dialog.close()
            self._update_progress_dialog.deleteLater()
            self._update_progress_dialog = None

        if not result.success or result.installer_path is None:
            self._set_update_busy(False, "Tải installer cập nhật thất bại.")
            MessageBox.warning(self, "Cập nhật ứng dụng", result.error or "Không tải được installer cập nhật.")
            if pending_result is not None and pending_result.is_forced_update:
                QTimer.singleShot(0, lambda: self._present_update_dialog(pending_result))
            return

        try:
            launcher_path = self._update_service.launch_installer_after_exit(result.installer_path)
        except RuntimeError as exc:
            LOGGER.exception("Không thể handoff updater sang launcher tạm")
            self._set_update_busy(False, "Không thể mở installer cập nhật.")
            MessageBox.error(self, "Cập nhật ứng dụng", str(exc))
            if pending_result is not None and pending_result.is_forced_update:
                QTimer.singleShot(0, lambda: self._present_update_dialog(pending_result))
            return

        LOGGER.info("Update launcher created at %s for installer %s", launcher_path, result.installer_path)
        self._set_update_busy(False, f"Đã tải xong phiên bản {result.version}.")
        MessageBox.info(
            self,
            "Cập nhật ứng dụng",
            "Installer mới đã được tải xong. Ứng dụng sẽ đóng để bắt đầu cài đè lên bản hiện tại.",
        )
        app = QCoreApplication.instance()
        if app is not None:
            QTimer.singleShot(0, app.quit)

    def _set_update_busy(self, busy: bool, message: str) -> None:
        if self._settings_page is not None and hasattr(self._settings_page, "set_update_busy"):
            self._settings_page.set_update_busy(busy, message)

    def _open_logs_directory(self) -> None:
        log_dir = self._diagnostics_service.log_directory()
        try:
            if hasattr(os, "startfile"):
                os.startfile(log_dir)  # type: ignore[attr-defined]
                return
            MessageBox.info(self, "Thư mục log", f"Thư mục log nằm tại:\n{log_dir}")
        except Exception as exc:
            MessageBox.error(self, "Không mở được thư mục log", str(exc))

    def _create_user_backup(self) -> None:
        if self._settings_page is not None and hasattr(self._settings_page, "set_backup_busy"):
            self._settings_page.set_backup_busy(True)
        try:
            result = self._backup_service.create_user_backup()
            details = [
                f"Đã tạo file sao lưu tại:\n{result.output_path}",
                f"Đã sao lưu: {', '.join(result.included_files) if result.included_files else 'không có file DB nào'}",
            ]
            if "attendance.db" in result.missing_files:
                details.append("Chưa có dữ liệu chấm công nên attendance.db chưa được sao lưu.")
            if "app.db" in result.missing_files:
                details.append("Không tìm thấy DB chính app.db trong thư mục dữ liệu.")
            MessageBox.info(self, "Sao lưu dữ liệu thành công", "\n\n".join(details))
        except Exception as exc:
            LOGGER.exception("Không tạo được sao lưu dữ liệu")
            MessageBox.error(self, "Không sao lưu được dữ liệu", str(exc))
        finally:
            if self._settings_page is not None and hasattr(self._settings_page, "set_backup_busy"):
                self._settings_page.set_backup_busy(False)

    def _export_diagnostics(self) -> None:
        if self._settings_page is not None and hasattr(self._settings_page, "set_diagnostics_busy"):
            self._settings_page.set_diagnostics_busy(True)
        try:
            archive_path = self._diagnostics_service.export_diagnostics()
            MessageBox.info(self, "Xuất chẩn đoán thành công", f"Đã tạo gói chẩn đoán tại:\n{archive_path}")
        except Exception as exc:
            MessageBox.error(self, "Không xuất được chẩn đoán", str(exc))
        finally:
            if self._settings_page is not None and hasattr(self._settings_page, "set_diagnostics_busy"):
                self._settings_page.set_diagnostics_busy(False)
