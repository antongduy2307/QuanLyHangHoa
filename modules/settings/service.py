from __future__ import annotations

from dataclasses import dataclass

from core.config import get_settings


@dataclass(frozen=True, slots=True)
class AppPreferences:
    app_name: str
    export_dir: str
    backup_dir: str


class SettingsService:
    def get_preferences(self) -> AppPreferences:
        settings = get_settings()
        return AppPreferences(
            app_name=settings.app_name,
            export_dir=str(settings.export_dir),
            backup_dir=str(settings.backup_dir),
        )
