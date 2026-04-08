from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMainWindow

from shell.history_page import HistoryPage
from shell.navigation import NavigationTabs

if TYPE_CHECKING:
    from shell.bootstrap import ModuleSpec


class AppWindow(QMainWindow):
    def __init__(self, title: str, modules: Sequence[ModuleSpec]) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1200, 720)

        tabs = NavigationTabs()
        for module_spec in modules:
            tabs.add_page(module_spec.label, module_spec.page_factory())

        tabs.add_page("Lịch sử", HistoryPage())
        self.setCentralWidget(tabs)
