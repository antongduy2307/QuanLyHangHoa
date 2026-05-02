from __future__ import annotations

from dataclasses import dataclass
from importlib import import_module
from typing import TYPE_CHECKING, Callable

from PyQt6.QtWidgets import QApplication, QWidget

from core.config import Settings, get_settings
from core.db import init_db
from core.logging import configure_logging, get_logger, install_exception_hooks, log_runtime_start
from shared.styles.theme import apply_theme

if TYPE_CHECKING:
    from shell.app_window import AppWindow

LOGGER = get_logger(__name__)

ACTIVE_MODULE_PACKAGES = (
    "modules.inventory",
    "modules.sales",
    "modules.customer",
    "modules.reporting",
    "modules.settings",
)


@dataclass(frozen=True, slots=True)
class ModuleSpec:
    key: str
    label: str
    page_factory: Callable[[], QWidget]


@dataclass(frozen=True, slots=True)
class AppContext:
    settings: Settings
    modules: tuple[ModuleSpec, ...]
    window: AppWindow



def load_module_specs() -> tuple[ModuleSpec, ...]:
    specs: list[ModuleSpec] = []
    for package_name in ACTIVE_MODULE_PACKAGES:
        package = import_module(package_name)
        specs.append(
            ModuleSpec(
                key=getattr(package, "MODULE_KEY"),
                label=getattr(package, "MODULE_LABEL"),
                page_factory=getattr(package, "create_page"),
            )
        )
    return tuple(specs)



def bootstrap_application(app: QApplication) -> AppContext:
    from shell.app_window import AppWindow

    settings = get_settings()
    configure_logging(settings.log_level, settings.log_dir)
    install_exception_hooks(settings.app_name)
    apply_theme(app)
    LOGGER.info(
        "Qt style initialized | style=%s | font=%s | pointSize=%s",
        app.style().objectName(),
        app.font().family(),
        app.font().pointSizeF(),
    )
    init_db()
    modules = load_module_specs()
    window = AppWindow(settings.app_name, modules, settings)
    log_runtime_start(app, settings)
    LOGGER.info("Application bootstrapped with %s modules", len(modules))
    return AppContext(settings=settings, modules=modules, window=window)


