from __future__ import annotations

from collections.abc import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTableWidget, QTableWidgetItem


class TableSelectionModeController:
    """Adds an explicit checkbox selection mode to a QTableWidget."""

    def __init__(
        self,
        table: QTableWidget,
        *,
        id_role: Qt.ItemDataRole = Qt.ItemDataRole.UserRole,
        id_source_column: int = 0,
        checkbox_column_title: str = "",
        on_selection_changed: Callable[[list[int]], None] | None = None,
    ) -> None:
        self._table = table
        self._id_role = id_role
        self._id_source_column = id_source_column
        self._checkbox_column_title = checkbox_column_title
        self._on_selection_changed = on_selection_changed
        self._selected_ids: set[int] = set()
        self._active = False
        self._updating = False

    @property
    def is_active(self) -> bool:
        return self._active

    def enter(self) -> None:
        if self._active:
            return
        self._active = True
        self._selected_ids.clear()
        self._table.insertColumn(0)
        self._table.setHorizontalHeaderItem(0, QTableWidgetItem(self._checkbox_column_title))
        self._populate_checkbox_column()
        self._table.itemChanged.connect(self._handle_item_changed)
        self._table.itemClicked.connect(self._handle_item_clicked)
        self._notify_selection_changed()

    def exit(self, *, clear: bool = True) -> None:
        if not self._active:
            if clear:
                self._selected_ids.clear()
                self._notify_selection_changed()
            return
        try:
            self._table.itemChanged.disconnect(self._handle_item_changed)
        except TypeError:
            pass
        try:
            self._table.itemClicked.disconnect(self._handle_item_clicked)
        except TypeError:
            pass
        self._active = False
        if self._table.columnCount() > 0:
            self._table.removeColumn(0)
        if clear:
            self._selected_ids.clear()
        self._notify_selection_changed()

    def clear_selection(self) -> None:
        self._selected_ids.clear()
        if self._active:
            self._updating = True
            try:
                for row in range(self._table.rowCount()):
                    item = self._table.item(row, 0)
                    if item is not None:
                        item.setCheckState(Qt.CheckState.Unchecked)
            finally:
                self._updating = False
        self._notify_selection_changed()

    def selected_ids(self) -> list[int]:
        ordered_ids: list[int] = []
        if self._active:
            for row in range(self._table.rowCount()):
                employee_id = self._row_id(row)
                if employee_id in self._selected_ids:
                    ordered_ids.append(employee_id)
        extras = sorted(self._selected_ids.difference(ordered_ids))
        return ordered_ids + extras

    def refresh_after_table_render(self) -> None:
        if not self._active:
            return
        self._populate_checkbox_column()
        self._selected_ids.intersection_update(self._visible_ids())
        self._notify_selection_changed()

    def _populate_checkbox_column(self) -> None:
        self._updating = True
        try:
            for row in range(self._table.rowCount()):
                row_id = self._row_id(row)
                checkbox_item = QTableWidgetItem()
                checkbox_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsUserCheckable
                )
                checkbox_item.setData(self._id_role, row_id)
                checkbox_item.setCheckState(
                    Qt.CheckState.Checked if row_id in self._selected_ids else Qt.CheckState.Unchecked
                )
                self._table.setItem(row, 0, checkbox_item)
        finally:
            self._updating = False

    def _handle_item_changed(self, item: QTableWidgetItem) -> None:
        if self._updating or not self._active or item.column() != 0:
            return
        row_id = item.data(self._id_role)
        if row_id is None:
            return
        normalized_id = int(row_id)
        if item.checkState() == Qt.CheckState.Checked:
            self._selected_ids.add(normalized_id)
        else:
            self._selected_ids.discard(normalized_id)
        self._notify_selection_changed()

    def _handle_item_clicked(self, item: QTableWidgetItem) -> None:
        if not self._active or item.column() == 0:
            return
        checkbox_item = self._table.item(item.row(), 0)
        if checkbox_item is None:
            return
        checkbox_item.setCheckState(
            Qt.CheckState.Unchecked
            if checkbox_item.checkState() == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )

    def _row_id(self, row: int) -> int | None:
        source_column = self._id_source_column + (1 if self._active else 0)
        item = self._table.item(row, source_column)
        if item is None:
            return None
        row_id = item.data(self._id_role)
        return int(row_id) if row_id is not None else None

    def _visible_ids(self) -> set[int]:
        ids: set[int] = set()
        for row in range(self._table.rowCount()):
            row_id = self._row_id(row)
            if row_id is not None:
                ids.add(row_id)
        return ids

    def _notify_selection_changed(self) -> None:
        if self._on_selection_changed is not None:
            self._on_selection_changed(self.selected_ids())
