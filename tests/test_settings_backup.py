from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from PyQt6.QtWidgets import QApplication, QPushButton

import core.config
from core.config import get_settings
from modules.attendance.db import get_attendance_engine, init_attendance_db, reset_attendance_engine_cache
from modules.settings.backup_service import UserBackupService
from modules.settings.service import SettingsService
from modules.settings.ui.page import SettingsPage


class SettingsBackupTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self._temp_root = Path("tests/_tmp/settings-backup").resolve()
        shutil.rmtree(self._temp_root, ignore_errors=True)
        self._temp_root.mkdir(parents=True, exist_ok=True)
        self._env_patch = patch.dict(os.environ, {"LOCALAPPDATA": str(self._temp_root)}, clear=False)
        self._env_patch.start()
        core.config.get_settings.cache_clear()
        reset_attendance_engine_cache()
        self.settings = get_settings()
        self.settings.app_data_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self) -> None:
        get_attendance_engine().dispose()
        reset_attendance_engine_cache()
        core.config.get_settings.cache_clear()
        self._env_patch.stop()
        shutil.rmtree(self._temp_root, ignore_errors=True)

    def _write_db_files(self, *, app_db: bool, attendance_db: bool) -> None:
        if app_db:
            self.settings.db_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings.db_path.write_bytes(b"main-db")
        if attendance_db:
            (self.settings.app_data_dir / "attendance.db").write_bytes(b"attendance-db")

    def _read_backup(self) -> tuple[set[str], dict[str, object]]:
        result = UserBackupService(self.settings).create_user_backup()
        self.assertTrue(result.output_path.exists())
        with ZipFile(result.output_path) as archive:
            names = set(archive.namelist())
            manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        return names, manifest

    def test_backup_includes_main_and_attendance_db_when_present(self) -> None:
        self._write_db_files(app_db=True, attendance_db=True)

        names, manifest = self._read_backup()

        self.assertEqual(names, {"app.db", "attendance.db", "manifest.json"})
        self.assertTrue(manifest["app_db_present"])
        self.assertTrue(manifest["attendance_db_present"])
        self.assertEqual(manifest["included_files"], ["app.db", "attendance.db"])
        self.assertEqual(manifest["missing_files"], [])

    def test_backup_succeeds_when_attendance_db_is_missing(self) -> None:
        self._write_db_files(app_db=True, attendance_db=False)

        names, manifest = self._read_backup()

        self.assertEqual(names, {"app.db", "manifest.json"})
        self.assertTrue(manifest["app_db_present"])
        self.assertFalse(manifest["attendance_db_present"])
        self.assertEqual(manifest["included_files"], ["app.db"])
        self.assertEqual(manifest["missing_files"], ["attendance.db"])

    def test_backup_succeeds_with_warning_when_main_db_is_missing(self) -> None:
        self._write_db_files(app_db=False, attendance_db=True)

        names, manifest = self._read_backup()

        self.assertEqual(names, {"attendance.db", "manifest.json"})
        self.assertFalse(manifest["app_db_present"])
        self.assertTrue(manifest["attendance_db_present"])
        self.assertEqual(manifest["included_files"], ["attendance.db"])
        self.assertEqual(manifest["missing_files"], ["app.db"])
        self.assertTrue(manifest["warnings"])

    def test_general_settings_has_backup_and_diagnostics_buttons(self) -> None:
        init_attendance_db()
        page = SettingsPage(SettingsService())
        button_texts = {button.text() for button in page.findChildren(QPushButton)}

        self.assertIn("Sao lưu dữ liệu", button_texts)
        self.assertIn("Xuất chẩn đoán", button_texts)


if __name__ == "__main__":
    unittest.main()
