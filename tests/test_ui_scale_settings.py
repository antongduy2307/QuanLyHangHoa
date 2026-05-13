from __future__ import annotations

import shutil
import tempfile
import unittest
from pathlib import Path

from PyQt6.QtCore import QCoreApplication, QSettings
from PyQt6.QtWidgets import QApplication, QPushButton, QTableWidget, QVBoxLayout, QWidget

from modules.settings.service import DEFAULT_UI_SCALE_PRESET, SettingsService, get_ui_scale_factor
from shared.widgets.ui_scale import apply_large_ui


class UiScaleSettingsTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])
        cls._app.setOrganizationName("CodexTests")
        cls._app.setApplicationName("QuanLyHangHoaUiScale")

    def setUp(self) -> None:
        self._tmp_dir = tempfile.TemporaryDirectory(prefix="ui-scale-settings-")
        self._settings_root = Path(self._tmp_dir.name)
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(self._settings_root))
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.SystemScope, str(self._settings_root))
        QSettings().clear()
        QSettings().sync()

    def tearDown(self) -> None:
        QSettings().clear()
        QSettings().sync()
        shutil.rmtree(self._settings_root, ignore_errors=True)
        self._tmp_dir.cleanup()

    def test_default_ui_scale_preset_uses_large_baseline(self) -> None:
        service = SettingsService()

        self.assertEqual(service.get_ui_scale_preset(), DEFAULT_UI_SCALE_PRESET)
        self.assertEqual(get_ui_scale_factor(service.get_ui_scale_preset()), 1.0)
        self.assertEqual(get_ui_scale_factor(), 1.0)

    def test_ui_scale_preset_persists_in_qsettings(self) -> None:
        service = SettingsService()
        service.set_ui_scale_preset("xlarge")

        reloaded = SettingsService()
        self.assertEqual(reloaded.get_ui_scale_preset(), "xlarge")
        self.assertEqual(get_ui_scale_factor("xlarge"), 1.25)

    def test_apply_large_ui_is_reversible_across_presets(self) -> None:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addWidget(QPushButton("Test"))
        table = QTableWidget(2, 2, widget)
        layout.addWidget(table)

        apply_large_ui(widget, "large")
        baseline_spacing = layout.spacing()
        baseline_row_height = table.verticalHeader().defaultSectionSize()

        apply_large_ui(widget, "standard")
        self.assertLess(layout.spacing(), baseline_spacing)
        self.assertLess(table.verticalHeader().defaultSectionSize(), baseline_row_height)

        apply_large_ui(widget, "large")
        self.assertEqual(layout.spacing(), baseline_spacing)
        self.assertEqual(table.verticalHeader().defaultSectionSize(), baseline_row_height)

        apply_large_ui(widget, "xlarge")
        self.assertGreater(layout.spacing(), baseline_spacing)
        self.assertGreater(table.verticalHeader().defaultSectionSize(), baseline_row_height)


if __name__ == "__main__":
    unittest.main()
