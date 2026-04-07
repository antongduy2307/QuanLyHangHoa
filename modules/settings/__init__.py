from __future__ import annotations

from modules.settings.service import SettingsService
from modules.settings.ui.page import SettingsPage

MODULE_KEY = "settings"
MODULE_LABEL = "Cai dat"



def create_page() -> SettingsPage:
    return SettingsPage(SettingsService())
