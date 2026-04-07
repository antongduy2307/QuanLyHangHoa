from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QFormLayout, QWidget

from modules.settings.service import SettingsService


class SettingsPage(QWidget):
    def __init__(self, service: SettingsService) -> None:
        super().__init__()
        preferences = service.get_preferences()

        layout = QFormLayout(self)
        layout.addRow("App name", QLabel(preferences.app_name))
        layout.addRow("Export dir", QLabel(preferences.export_dir))
        layout.addRow("Backup dir", QLabel(preferences.backup_dir))
