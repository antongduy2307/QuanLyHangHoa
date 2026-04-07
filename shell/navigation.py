from __future__ import annotations

from PyQt6.QtWidgets import QTabWidget, QWidget


class NavigationTabs(QTabWidget):
    def add_page(self, label: str, widget: QWidget) -> None:
        self.addTab(widget, label)
