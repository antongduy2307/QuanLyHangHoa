from __future__ import annotations

import sys

from PyQt6.QtWidgets import QMessageBox, QWidget

from core.logging import get_logger


LOGGER = get_logger(__name__)


class MessageBox:
    @staticmethod
    def info(parent: QWidget | None, title: str, message: str) -> None:
        QMessageBox.information(parent, title, message)

    @staticmethod
    def warning(parent: QWidget | None, title: str, message: str) -> None:
        QMessageBox.warning(parent, title, message)

    @staticmethod
    def error(parent: QWidget | None, title: str, message: str) -> None:
        exc_info = sys.exc_info()
        if exc_info[0] is not None and exc_info[1] is not None and exc_info[2] is not None:
            LOGGER.error("%s | %s", title, message, exc_info=exc_info)
        else:
            LOGGER.error("%s | %s", title, message)
        QMessageBox.critical(parent, title, message)
