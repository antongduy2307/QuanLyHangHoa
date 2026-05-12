from __future__ import annotations

import json
import logging
from pathlib import Path
import shutil
import sys
from tempfile import TemporaryDirectory
import threading
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PyQt6.QtWidgets import QApplication, QMessageBox

from core.config import Settings
from core.logging import configure_logging, get_log_file_path, get_logger, install_exception_hooks
from modules.diagnostics.service import DiagnosticsService
from shared.widgets.message_box import MessageBox


class DiagnosticsServiceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._tmp_dir = TemporaryDirectory()
        self.test_root = Path(self._tmp_dir.name)

    def tearDown(self) -> None:
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        self._tmp_dir.cleanup()

    def _build_settings(self, root: Path) -> Settings:
        app_data_dir = root / "appdata"
        return Settings(
            app_name="Quan ly Hang hoa",
            app_data_dir=app_data_dir,
            db_path=app_data_dir / "app.db",
            log_dir=app_data_dir / "logs",
            export_dir=app_data_dir / "exports",
            backup_dir=app_data_dir / "backups",
            temp_dir=app_data_dir / "temp",
            log_level="INFO",
            update_manifest_url="https://example.invalid/version.json",
            update_check_timeout_ms=1000,
            update_download_timeout_ms=1000,
            update_download_retry_count=2,
            update_startup_delay_ms=1000,
        )

    def _make_test_root(self, name: str) -> Path:
        root = self.test_root / name
        if root.exists():
            shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return root

    def test_export_diagnostics_creates_zip_with_expected_files(self) -> None:
        root = self._make_test_root("export")
        try:
            settings = self._build_settings(root)
            log_path = configure_logging(settings.log_level, settings.log_dir)
            get_logger("tests.diagnostics").info("diagnostics export smoke")

            service = DiagnosticsService(settings, self._app)
            archive_path = service.export_diagnostics()

            self.assertTrue(log_path.exists())
            self.assertTrue(archive_path.exists())
            with ZipFile(archive_path) as archive:
                names = set(archive.namelist())
                self.assertEqual(names, {"app_info.json", "ui_environment.json", "recent_log.txt"})
                app_info = json.loads(archive.read("app_info.json").decode("utf-8"))
                ui_environment = json.loads(archive.read("ui_environment.json").decode("utf-8"))
                recent_log = archive.read("recent_log.txt").decode("utf-8")

            self.assertEqual(app_info["log_dir"], str(settings.log_dir))
            self.assertEqual(app_info["db_path"], str(settings.db_path))
            self.assertIn("ui_scale_preset", app_info)
            self.assertIn("screen", ui_environment)
            self.assertIn("diagnostics export smoke", recent_log)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_message_box_error_logs_traceback_when_called_inside_except(self) -> None:
        root = self._make_test_root("message_box")
        try:
            settings = self._build_settings(root)
            configure_logging(settings.log_level, settings.log_dir)

            with patch.object(QMessageBox, "critical"):
                try:
                    raise RuntimeError("boom message box")
                except RuntimeError as exc:
                    MessageBox.error(None, "Lỗi test", str(exc))

            log_contents = (get_log_file_path() or settings.log_dir / "app.log").read_text(encoding="utf-8", errors="replace")
            self.assertIn("boom message box", log_contents)
            self.assertIn("Traceback", log_contents)
        finally:
            shutil.rmtree(root, ignore_errors=True)

    def test_global_exception_hook_logs_unhandled_traceback(self) -> None:
        root = self._make_test_root("global_hook")
        try:
            settings = self._build_settings(root)
            configure_logging(settings.log_level, settings.log_dir)

            original_excepthook = sys.excepthook
            original_threading_hook = threading.excepthook
            try:
                install_exception_hooks(settings.app_name)
                with patch.object(QMessageBox, "critical"):
                    try:
                        raise ValueError("boom global")
                    except ValueError as exc:
                        sys.excepthook(type(exc), exc, exc.__traceback__)
            finally:
                sys.excepthook = original_excepthook
                threading.excepthook = original_threading_hook

            log_contents = (get_log_file_path() or settings.log_dir / "app.log").read_text(encoding="utf-8", errors="replace")
            self.assertIn("Unhandled exception", log_contents)
            self.assertIn("boom global", log_contents)
        finally:
            shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
