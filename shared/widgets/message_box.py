from __future__ import annotations

from PyQt6.QtWidgets import QMessageBox, QWidget


class MessageBox:
    @staticmethod
    def info(parent: QWidget | None, title: str, message: str) -> None:
        QMessageBox.information(parent, title, message)

    @staticmethod
    def warning(parent: QWidget | None, title: str, message: str) -> None:
        QMessageBox.warning(parent, title, message)

    @staticmethod
    def error(parent: QWidget | None, title: str, message: str) -> None:
        QMessageBox.critical(parent, title, message)
