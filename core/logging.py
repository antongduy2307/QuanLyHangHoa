from __future__ import annotations

import io
import logging as std_logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import platform
import sys
import threading
import traceback

from PyQt6.QtCore import QT_VERSION_STR, PYQT_VERSION_STR
from PyQt6.QtWidgets import QApplication, QMessageBox

from core.config import Settings
from core.version import APP_VERSION
from modules.settings.service import get_ui_scale_preset


_LOG_FILE_PATH: Path | None = None
_ORIGINAL_EXCEPTHOOK = sys.excepthook
_ORIGINAL_THREADING_EXCEPTHOOK = threading.excepthook


class _SafeConsoleStream:
    def __init__(self, stream: io.TextIOBase) -> None:
        self._stream = stream

    def write(self, message: str) -> int:
        try:
            return self._stream.write(message)
        except UnicodeEncodeError:
            encoded = message.encode(getattr(self._stream, "encoding", None) or "utf-8", errors="replace")
            if hasattr(self._stream, "buffer"):
                self._stream.buffer.write(encoded)
                return len(message)
            return self._stream.write(encoded.decode("ascii", errors="replace"))

    def flush(self) -> None:
        self._stream.flush()


def configure_logging(level: str = "INFO", log_dir: Path | None = None) -> Path:
    global _LOG_FILE_PATH

    resolved_dir = log_dir or Path.cwd() / "logs"
    resolved_dir.mkdir(parents=True, exist_ok=True)
    _LOG_FILE_PATH = resolved_dir / "app.log"

    root_logger = std_logging.getLogger()
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()
    root_logger.setLevel(getattr(std_logging, level.upper(), std_logging.INFO))

    formatter = std_logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")

    file_handler = RotatingFileHandler(_LOG_FILE_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    stream_handler = std_logging.StreamHandler(_SafeConsoleStream(sys.stdout))
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    root_logger.info("Logging configured at %s", _LOG_FILE_PATH)
    return _LOG_FILE_PATH


def get_logger(name: str) -> std_logging.Logger:
    return std_logging.getLogger(name)


def get_log_file_path() -> Path | None:
    return _LOG_FILE_PATH


def install_exception_hooks(app_name: str) -> None:
    def _handle_exception(exc_type: type[BaseException], exc_value: BaseException, exc_traceback: object) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            _ORIGINAL_EXCEPTHOOK(exc_type, exc_value, exc_traceback)
            return
        logger = get_logger("runtime.unhandled")
        logger.critical("Unhandled exception in %s", app_name, exc_info=(exc_type, exc_value, exc_traceback))
        try:
            QMessageBox.critical(
                None,
                "Lỗi không mong muốn",
                "Ứng dụng vừa gặp lỗi không mong muốn. Vui lòng vào Cài đặt để xuất chẩn đoán và gửi lại cho dev.",
            )
        except Exception:
            logger.error("Unable to display crash message box.\n%s", traceback.format_exc())

    def _handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        _handle_exception(args.exc_type, args.exc_value, args.exc_traceback)

    sys.excepthook = _handle_exception
    threading.excepthook = _handle_thread_exception


def log_runtime_start(app: QApplication, settings: Settings) -> None:
    logger = get_logger("runtime.startup")
    screen = app.primaryScreen()
    screen_size = None
    available_size = None
    logical_dpi = None
    device_pixel_ratio = None

    if screen is not None:
        geometry = screen.geometry()
        available_geometry = screen.availableGeometry()
        screen_size = {"width": geometry.width(), "height": geometry.height()}
        available_size = {"width": available_geometry.width(), "height": available_geometry.height()}
        logical_dpi = {
            "x": round(screen.logicalDotsPerInchX(), 2),
            "y": round(screen.logicalDotsPerInchY(), 2),
        }
        device_pixel_ratio = round(screen.devicePixelRatio(), 3)

    logger.info("Application start")
    logger.info("APP_VERSION=%s", APP_VERSION)
    logger.info("Platform=%s", platform.platform())
    logger.info("Python=%s", platform.python_version())
    logger.info("Qt=%s | PyQt=%s", QT_VERSION_STR, PYQT_VERSION_STR)
    logger.info("Executable=%s", Path(sys.executable).resolve())
    logger.info("AppDataDir=%s", settings.app_data_dir)
    logger.info("DBPath=%s", settings.db_path)
    logger.info("LogFile=%s", _LOG_FILE_PATH)
    logger.info("UIScalePreset=%s", get_ui_scale_preset())
    logger.info("Screen=%s | AvailableGeometry=%s", screen_size, available_size)
    logger.info("LogicalDPI=%s | DevicePixelRatio=%s", logical_dpi, device_pixel_ratio)
