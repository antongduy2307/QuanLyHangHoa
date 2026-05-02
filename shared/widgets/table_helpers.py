from __future__ import annotations

import json
from typing import Sequence

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QObject, QPoint, QSettings, QTimer, Qt
from PyQt6.QtGui import QFontMetrics
from PyQt6.QtWidgets import QAbstractItemView, QComboBox, QHeaderView, QLineEdit, QMenu, QPushButton, QSizePolicy, QTableView, QTableWidget, QWidget


_TABLE_WIDTH_STATE_VERSION = 2


class _FullWidthResizeController(QObject):
    def __init__(self, table: QTableWidget | QTableView, persistence_key: str | None = None) -> None:
        super().__init__(table)
        self._table = table
        self._viewport = table.viewport()
        self._header = table.horizontalHeader()
        self._settings = QSettings()
        self._persistence_key = persistence_key or table.objectName() or None
        self._adjusting = False
        self._initialized = False
        self._using_default_layout = True
        self._min_widths: dict[int, int] = {}

        header = self._header_ref()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            header.setStretchLastSection(False)
            header.sectionResized.connect(self._on_section_resized)
            header.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
            header.customContextMenuRequested.connect(self._show_header_menu)

        table.installEventFilter(self)
        self._viewport_ref() and self._viewport.installEventFilter(self)
        table.destroyed.connect(self._cleanup_filters)
        QTimer.singleShot(0, self._finalize_initial_layout)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        table = self._table_ref()
        viewport = self._viewport_ref()
        if table is None or viewport is None:
            return False
        if watched in {table, viewport} and event.type() == QEvent.Type.Resize and self._initialized:
            if self._using_default_layout:
                self._apply_widths(self._build_default_widths())
            else:
                self._ensure_full_width()
            self._save_widths()
        return super().eventFilter(watched, event)

    def reset_to_default(self) -> None:
        self._clear_saved_widths()
        self._using_default_layout = True
        self._initialized = False
        header = self._header_ref()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        QTimer.singleShot(0, self._finalize_initial_layout)

    def _finalize_initial_layout(self) -> None:
        table = self._table_ref()
        header = self._header_ref()
        viewport = self._viewport_ref()
        if table is None or header is None or viewport is None:
            return
        if header.count() <= 0 or viewport.width() <= 0:
            QTimer.singleShot(0, self._finalize_initial_layout)
            return

        self._min_widths = self._calculate_min_widths()
        restored_widths = self._restore_widths()
        if restored_widths is None:
            widths = self._build_default_widths()
            self._using_default_layout = True
        else:
            widths = self._fit_widths_to_viewport(restored_widths)
            self._using_default_layout = False

        self._apply_widths(widths)
        self._initialized = True
        self._save_widths()

    def _calculate_min_widths(self) -> dict[int, int]:
        table = self._table_ref()
        header = self._header_ref()
        if table is None or header is None:
            return {}
        metrics = QFontMetrics(header.font())
        widths: dict[int, int] = {}
        for index in range(header.count()):
            header_text = str(table.model().headerData(index, Qt.Orientation.Horizontal) or "")
            widths[index] = max(80, metrics.horizontalAdvance(header_text) + 28)
        custom_widths = table.property("column_minimum_widths")
        if isinstance(custom_widths, dict):
            for index, width in custom_widths.items():
                widths[int(index)] = max(widths.get(int(index), 80), int(width))
        return widths

    def _build_default_widths(self) -> list[int]:
        header = self._header_ref()
        viewport = self._viewport_ref()
        if header is None or viewport is None:
            return []
        count = header.count()
        viewport_width = max(viewport.width(), 1)
        equal_width = max(1, viewport_width // max(count, 1))
        widths = [equal_width for _ in range(count)]
        return self._fit_widths_to_viewport(widths)

    def _fit_widths_to_viewport(self, widths: Sequence[int]) -> list[int]:
        viewport = self._viewport_ref()
        if viewport is None:
            return list(widths)
        fitted = [max(int(width), self._min_widths.get(index, 80)) for index, width in enumerate(widths)]
        viewport_width = max(viewport.width(), 1)
        total_width = sum(fitted)

        if total_width < viewport_width:
            extra = viewport_width - total_width
            share, remainder = divmod(extra, max(len(fitted), 1))
            for index in range(len(fitted)):
                fitted[index] += share
                if index < remainder:
                    fitted[index] += 1
            return fitted

        if total_width > viewport_width:
            remaining = total_width - viewport_width
            while remaining > 0:
                changed = False
                for index in reversed(range(len(fitted))):
                    minimum = self._min_widths.get(index, 80)
                    if fitted[index] > minimum:
                        fitted[index] -= 1
                        remaining -= 1
                        changed = True
                        if remaining == 0:
                            break
                if not changed:
                    break
        return fitted

    def _restore_widths(self) -> list[int] | None:
        header = self._header_ref()
        if header is None or not self._persistence_key:
            return None
        raw = self._settings.value(self._settings_key())
        if not raw:
            return None
        if not isinstance(raw, str):
            return None
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("version") != _TABLE_WIDTH_STATE_VERSION:
            return None
        widths = payload.get("widths")
        if not isinstance(widths, list):
            return None
        try:
            normalized = [int(width) for width in widths]
        except (TypeError, ValueError):
            return None
        if len(normalized) != header.count():
            return None
        return normalized

    def _save_widths(self) -> None:
        header = self._header_ref()
        if header is None or not self._persistence_key or not self._initialized:
            return
        widths = [header.sectionSize(index) for index in range(header.count())]
        payload = json.dumps({"version": _TABLE_WIDTH_STATE_VERSION, "widths": widths})
        self._settings.setValue(self._settings_key(), payload)

    def _clear_saved_widths(self) -> None:
        if not self._persistence_key:
            return
        self._settings.remove(self._settings_key())

    def _settings_key(self) -> str:
        return f"table_widths/{self._persistence_key}"

    def _apply_widths(self, widths: Sequence[int]) -> None:
        header = self._header_ref()
        if header is None:
            return
        self._adjusting = True
        try:
            for index, width in enumerate(widths):
                header.setSectionResizeMode(index, QHeaderView.ResizeMode.Interactive)
                header.resizeSection(index, width)
        finally:
            self._adjusting = False
        self._ensure_full_width()

    def _on_section_resized(self, logical_index: int, _old_size: int, new_size: int) -> None:
        header = self._header_ref()
        if header is None:
            return
        if not self._initialized or self._adjusting:
            return
        minimum = self._min_widths.get(logical_index, 80)
        if new_size < minimum:
            self._adjusting = True
            try:
                header.resizeSection(logical_index, minimum)
            finally:
                self._adjusting = False
        self._using_default_layout = False
        self._ensure_full_width(exclude=logical_index)
        self._save_widths()

    def _ensure_full_width(self, exclude: int | None = None) -> None:
        header = self._header_ref()
        viewport = self._viewport_ref()
        if header is None or viewport is None:
            return
        if self._adjusting or not self._initialized:
            return
        viewport_width = viewport.width()
        if viewport_width <= 0:
            return
        total_width = sum(header.sectionSize(index) for index in range(header.count()))
        delta = viewport_width - total_width
        if delta == 0:
            return

        self._adjusting = True
        try:
            candidates = [index for index in reversed(range(header.count())) if index != exclude]
            if not candidates and exclude is not None:
                candidates = [exclude]

            if delta > 0:
                target = candidates[0] if candidates else 0
                header.resizeSection(target, header.sectionSize(target) + delta)
                return

            remaining = -delta
            shrink_order = candidates + ([exclude] if exclude is not None and exclude not in candidates else [])
            for index in shrink_order:
                current = header.sectionSize(index)
                minimum = self._min_widths.get(index, 80)
                shrink = min(remaining, max(0, current - minimum))
                if shrink <= 0:
                    continue
                header.resizeSection(index, current - shrink)
                remaining -= shrink
                if remaining == 0:
                    break
        finally:
            self._adjusting = False

    def _show_header_menu(self, position: QPoint) -> None:
        header = self._header_ref()
        if header is None:
            return
        menu = QMenu(header)
        reset_action = menu.addAction("Đặt lại độ rộng cột")
        chosen = menu.exec(header.mapToGlobal(position))
        if chosen == reset_action:
            self.reset_to_default()

    def _cleanup_filters(self, *_args: object) -> None:
        table = self._table_ref()
        viewport = self._viewport_ref()
        if table is not None:
            table.removeEventFilter(self)
        if viewport is not None:
            viewport.removeEventFilter(self)

    def _table_ref(self) -> QTableWidget | QTableView | None:
        table = self._table
        if table is None or sip.isdeleted(table):
            self._table = None
            return None
        return table

    def _viewport_ref(self):
        viewport = self._viewport
        if viewport is None or sip.isdeleted(viewport):
            self._viewport = None
            return None
        return viewport

    def _header_ref(self):
        header = self._header
        if header is None or sip.isdeleted(header):
            self._header = None
            return None
        return header



def configure_table_widget(table: QTableWidget, persistence_key: str | None = None) -> None:
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.verticalHeader().setVisible(False)
    _setup_resizable_table(table, persistence_key)



def configure_table_view(table: QTableView, persistence_key: str | None = None) -> None:
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.verticalHeader().setVisible(False)
    _setup_resizable_table(table, persistence_key)



def reset_table_widths(table: QTableWidget | QTableView) -> None:
    controller = getattr(table, '_full_width_resize_controller', None)
    if controller is not None:
        controller.reset_to_default()



def _setup_resizable_table(table: QTableWidget | QTableView, persistence_key: str | None = None) -> None:
    if getattr(table, '_full_width_resize_controller', None) is not None:
        return
    setattr(table, '_full_width_resize_controller', _FullWidthResizeController(table, persistence_key))


def configure_table_cell_widget(widget: QWidget, *, compact: bool = False, height: int = 34) -> None:
    horizontal_policy = QSizePolicy.Policy.MinimumExpanding if compact else QSizePolicy.Policy.Expanding
    widget.setSizePolicy(horizontal_policy, QSizePolicy.Policy.Fixed)
    widget.setMinimumWidth(0)
    widget.setContentsMargins(0, 0, 0, 0)
    widget.setMinimumHeight(height)
    widget.setMaximumHeight(height)

    if isinstance(widget, QLineEdit):
        widget.setFrame(False)
        widget.setStyleSheet(
            "margin: 0;"
            "padding: 0 6px;"
            "border: none;"
            "border-radius: 0;"
            "background: transparent;"
        )
    elif isinstance(widget, QComboBox):
        widget.setStyleSheet(
            "margin: 0;"
            "padding: 0 18px 0 6px;"
            "border: none;"
            "border-radius: 0;"
            "background: transparent;"
            "selection-background-color: transparent;"
            "selection-color: palette(text);"
            "QComboBox::drop-down {"
            " border: none;"
            " background: transparent;"
            " width: 14px;"
            " subcontrol-origin: padding;"
            " subcontrol-position: top right;"
            "}"
            "QComboBox::down-arrow {"
            " width: 8px;"
            " height: 8px;"
            " margin-right: 2px;"
            "}"
        )
    elif isinstance(widget, QPushButton):
        widget.setStyleSheet(
            "margin: 0;"
            "padding: 0 8px;"
            "border: none;"
            "border-radius: 0;"
            "background: transparent;"
        )
