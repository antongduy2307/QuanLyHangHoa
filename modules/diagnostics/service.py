from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import platform
import sys
from zipfile import ZIP_DEFLATED, ZipFile

from PyQt6.QtCore import PYQT_VERSION_STR, QT_VERSION_STR
from PyQt6.QtWidgets import QApplication

from core.config import Settings
from core.logging import get_log_file_path, get_logger
from core.version import APP_VERSION
from modules.settings.service import get_ui_scale_preset


LOGGER = get_logger(__name__)


class DiagnosticsService:
    def __init__(self, settings: Settings, app: QApplication) -> None:
        self._settings = settings
        self._app = app

    def log_directory(self) -> Path:
        self._settings.log_dir.mkdir(parents=True, exist_ok=True)
        return self._settings.log_dir

    def export_diagnostics(self) -> Path:
        export_dir = self._settings.export_dir / "diagnostics"
        export_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        archive_path = export_dir / f"diagnostics-{timestamp}.zip"

        app_info = self._build_app_info()
        ui_environment = self._build_ui_environment()
        recent_log = self._read_recent_log_tail()

        with ZipFile(archive_path, "w", compression=ZIP_DEFLATED) as archive:
            archive.writestr("app_info.json", json.dumps(app_info, indent=2, ensure_ascii=False))
            archive.writestr("ui_environment.json", json.dumps(ui_environment, indent=2, ensure_ascii=False))
            archive.writestr("recent_log.txt", recent_log)

        LOGGER.info("Diagnostics exported to %s", archive_path)
        return archive_path

    def _build_app_info(self) -> dict[str, object]:
        return {
            "timestamp": datetime.now().isoformat(),
            "app_name": self._settings.app_name,
            "app_version": APP_VERSION,
            "os_name": platform.system(),
            "os_version": platform.version(),
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "qt_version": QT_VERSION_STR,
            "pyqt_version": PYQT_VERSION_STR,
            "executable_path": str(Path(sys.executable).resolve()),
            "app_data_dir": str(self._settings.app_data_dir),
            "db_path": str(self._settings.db_path),
            "log_dir": str(self.log_directory()),
            "log_file": str(get_log_file_path() or (self.log_directory() / "app.log")),
            "ui_scale_preset": get_ui_scale_preset(),
        }

    def _build_ui_environment(self) -> dict[str, object]:
        screen = self._app.primaryScreen()
        if screen is None:
            return {
                "timestamp": datetime.now().isoformat(),
                "ui_scale_preset": get_ui_scale_preset(),
                "screen": None,
                "available_geometry": None,
                "logical_dpi": None,
                "device_pixel_ratio": None,
            }

        geometry = screen.geometry()
        available_geometry = screen.availableGeometry()
        return {
            "timestamp": datetime.now().isoformat(),
            "ui_scale_preset": get_ui_scale_preset(),
            "screen": {"width": geometry.width(), "height": geometry.height()},
            "available_geometry": {"width": available_geometry.width(), "height": available_geometry.height()},
            "logical_dpi": {
                "x": round(screen.logicalDotsPerInchX(), 2),
                "y": round(screen.logicalDotsPerInchY(), 2),
            },
            "device_pixel_ratio": round(screen.devicePixelRatio(), 3),
        }

    def _read_recent_log_tail(self, max_lines: int = 400) -> str:
        log_file = get_log_file_path() or (self.log_directory() / "app.log")
        if not log_file.exists():
            return "No log file found."
        lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[-max_lines:])
