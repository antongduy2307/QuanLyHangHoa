from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QSettings

from core.config import get_settings


UI_SCALE_OPTIONS: tuple[tuple[str, str, float], ...] = (
    ("standard", "Chuẩn", 0.85),
    ("large", "To", 1.0),
    ("xlarge", "Rất to", 1.25),
)
DEFAULT_UI_SCALE_PRESET = "large"
_UI_SCALE_KEY = "ui/scale_preset"
_UI_SCALE_FACTORS = {key: factor for key, _label, factor in UI_SCALE_OPTIONS}
_VALID_UI_SCALE_PRESETS = set(_UI_SCALE_FACTORS)


@dataclass(frozen=True, slots=True)
class AppPreferences:
    app_name: str
    log_dir: str
    export_dir: str
    backup_dir: str
    ui_scale_preset: str


class SettingsService:
    def __init__(self) -> None:
        self._settings = QSettings()

    def get_preferences(self) -> AppPreferences:
        settings = get_settings()
        return AppPreferences(
            app_name=settings.app_name,
            log_dir=str(settings.log_dir),
            export_dir=str(settings.export_dir),
            backup_dir=str(settings.backup_dir),
            ui_scale_preset=self.get_ui_scale_preset(),
        )

    def get_ui_scale_preset(self) -> str:
        preset = str(self._settings.value(_UI_SCALE_KEY, DEFAULT_UI_SCALE_PRESET))
        if preset not in _VALID_UI_SCALE_PRESETS:
            return DEFAULT_UI_SCALE_PRESET
        return preset

    def set_ui_scale_preset(self, preset: str) -> None:
        if preset not in _VALID_UI_SCALE_PRESETS:
            raise ValueError("ui scale preset không hợp lệ")
        self._settings.setValue(_UI_SCALE_KEY, preset)




def get_ui_scale_preset() -> str:
    return SettingsService().get_ui_scale_preset()


def get_ui_scale_factor(preset: str | None = None) -> float:
    normalized = preset or SettingsService().get_ui_scale_preset()
    return _UI_SCALE_FACTORS.get(normalized, _UI_SCALE_FACTORS[DEFAULT_UI_SCALE_PRESET])



def get_ui_scale_label(preset: str | None = None) -> str:
    normalized = preset or SettingsService().get_ui_scale_preset()
    for key, label, _factor in UI_SCALE_OPTIONS:
        if key == normalized:
            return label
    return "To"

