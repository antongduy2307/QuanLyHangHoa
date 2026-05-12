from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import core.config
import core.db
from core.paths import migrate_legacy_runtime_dir


class RuntimePathsTestCase(unittest.TestCase):
    def tearDown(self) -> None:
        core.config.get_settings.cache_clear()

    def test_migrate_legacy_runtime_dir_copies_full_directory_when_new_missing(self) -> None:
        temp_root = Path(tempfile.mkdtemp(prefix="runtime-paths-"))
        try:
            legacy_dir = temp_root / "Quan ly Hang hoa"
            current_dir = temp_root / "QuanLyHangHoa"
            legacy_dir.mkdir(parents=True, exist_ok=True)
            (legacy_dir / "app.db").write_bytes(b"db-bytes")
            (legacy_dir / "logs").mkdir()
            (legacy_dir / "logs" / "app.log").write_text("hello", encoding="utf-8")

            migrated = migrate_legacy_runtime_dir(current_dir=current_dir, legacy_dir=legacy_dir)

            self.assertTrue(migrated)
            self.assertTrue((current_dir / "app.db").exists())
            self.assertEqual((current_dir / "app.db").read_bytes(), b"db-bytes")
            self.assertEqual((current_dir / "logs" / "app.log").read_text(encoding="utf-8"), "hello")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_get_settings_uses_ascii_runtime_dir_and_migrates_legacy_db(self) -> None:
        temp_root = Path(tempfile.mkdtemp(prefix="runtime-settings-"))
        try:
            legacy_name = "Quan ly Hang hoa"
            legacy_dir = temp_root / legacy_name
            legacy_dir.mkdir(parents=True, exist_ok=True)
            (legacy_dir / "app.db").write_bytes(b"legacy-db")

            with patch.dict(os.environ, {"LOCALAPPDATA": str(temp_root), "APP_NAME": legacy_name}, clear=False):
                core.config.get_settings.cache_clear()
                settings = core.config.get_settings()

            self.assertEqual(settings.runtime_dir_name, "QuanLyHangHoa")
            self.assertEqual(settings.app_data_dir, temp_root / "QuanLyHangHoa")
            self.assertTrue(settings.db_path.parent.exists())
            self.assertTrue(settings.db_path.exists())
            self.assertEqual(settings.db_path.read_bytes(), b"legacy-db")
        finally:
            shutil.rmtree(temp_root, ignore_errors=True)

    def test_get_settings_calculates_db_path_without_creating_db_file(self) -> None:
        temp_root = Path(tempfile.mkdtemp(prefix="runtime-settings-empty-"))
        try:
            with patch.dict(os.environ, {"LOCALAPPDATA": str(temp_root)}, clear=False):
                core.config.get_settings.cache_clear()
                settings = core.config.get_settings()

                self.assertEqual(settings.db_path, temp_root / "QuanLyHangHoa" / "app.db")
                self.assertFalse(settings.db_path.exists())

                core.db.reset_engine_cache()
                self.assertTrue(settings.db_path.parent.exists())
        finally:
            core.config.get_settings.cache_clear()
            core.db.reset_engine_cache()
            shutil.rmtree(temp_root, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
