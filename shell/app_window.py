from __future__ import annotations

from collections.abc import Sequence
from importlib import import_module
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QMainWindow

from shell.navigation import NavigationTabs

if TYPE_CHECKING:
    from shell.bootstrap import ModuleSpec


class AppWindow(QMainWindow):
    def __init__(self, title: str, modules: Sequence[ModuleSpec]) -> None:
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1200, 720)

        tabs = NavigationTabs()
        seen_keys: set[str] = set()
        for module_spec in modules:
            seen_keys.add(module_spec.key)
            tabs.add_page(module_spec.label, module_spec.page_factory())

        if "returns" not in seen_keys:
            returns_module = import_module("modules.returns")
            tabs.add_page(getattr(returns_module, "MODULE_LABEL"), getattr(returns_module, "create_page")())

        self.setCentralWidget(tabs)
