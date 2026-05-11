from __future__ import annotations

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QLineEdit, QListWidget, QListWidgetItem


class AutocompleteLineEdit(QLineEdit):
    suggestion_selected = pyqtSignal(object)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._app = QApplication.instance()
        self._popup: QListWidget | None = QListWidget()
        self._popup_minimum_width = 420
        self._popup.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
        )
        self._popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._popup.setMaximumHeight(220)
        self._popup.itemClicked.connect(self._choose_item)
        self._popup.itemActivated.connect(self._choose_item)
        self._popup.destroyed.connect(self._handle_popup_destroyed)
        self.installEventFilter(self)
        if self._app is not None:
            self._app.installEventFilter(self)
        self.destroyed.connect(self._cleanup_filters)

    def set_suggestions(self, items: list[tuple[str, object]]) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        popup.clear()
        if not self.text().strip() or not items:
            self.hide_suggestions()
            return
        for label, data in items[:20]:
            item = QListWidgetItem(label)
            item.setData(Qt.ItemDataRole.UserRole, data)
            popup.addItem(item)
        popup.setCurrentRow(0)
        self._position_popup()
        popup.show()
        popup.raise_()
        self._restore_input_focus()
        QTimer.singleShot(0, self._restore_input_focus)

    def hide_suggestions(self) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        popup.hide()
        popup.clearSelection()

    def set_popup_minimum_width(self, width: int) -> None:
        self._popup_minimum_width = max(0, int(width))

    def set_popup_maximum_height(self, height: int) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        popup.setMaximumHeight(max(0, int(height)))

    def set_popup_stylesheet(self, stylesheet: str) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        popup.setStyleSheet(stylesheet)

    def eventFilter(self, watched: object, event: object) -> bool:
        popup = self._popup_ref()
        if popup is None:
            return super().eventFilter(watched, event)

        if watched is self and isinstance(event, QKeyEvent):
            if popup.isVisible():
                if event.key() == Qt.Key.Key_Down:
                    self._move_selection(1)
                    return True
                if event.key() == Qt.Key.Key_Up:
                    self._move_selection(-1)
                    return True
                if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                    self._activate_current()
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self.hide_suggestions()
                    return True
        if watched is self and isinstance(event, QEvent):
            if event.type() in {QEvent.Type.Move, QEvent.Type.Resize} and popup.isVisible():
                self._position_popup()
        if popup.isVisible() and isinstance(event, QMouseEvent) and event.type() == QEvent.Type.MouseButtonPress:
            global_pos = event.globalPosition().toPoint()
            if not self._is_inside_input_or_popup(global_pos):
                self.hide_suggestions()
        return super().eventFilter(watched, event)

    def _position_popup(self) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        popup_width = max(self.width(), self._popup_minimum_width)
        row_count = min(max(popup.count(), 1), 6)
        row_height = popup.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 28
        frame = popup.frameWidth() * 2
        popup_height = row_count * row_height + frame + 4
        global_pos = self.mapToGlobal(QPoint(0, self.height()))
        popup.setGeometry(global_pos.x(), global_pos.y(), popup_width, popup_height)

    def _is_inside_input_or_popup(self, global_pos: QPoint) -> bool:
        popup = self._popup_ref()
        if popup is None:
            return False
        input_pos = self.mapToGlobal(QPoint(0, 0))
        input_rect = self.rect().translated(input_pos)
        return input_rect.contains(global_pos) or popup.geometry().contains(global_pos)

    def _move_selection(self, delta: int) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        count = popup.count()
        if count == 0:
            return
        current_row = popup.currentRow()
        if current_row < 0:
            current_row = 0
        next_row = max(0, min(count - 1, current_row + delta))
        popup.setCurrentRow(next_row)

    def _activate_current(self) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        item = popup.currentItem()
        if item is not None:
            self._choose_item(item)

    def _choose_item(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        item_text = item.text()
        user_data = item.data(Qt.ItemDataRole.UserRole)
        self.hide_suggestions()
        self.setText(item_text)
        self.suggestion_selected.emit(user_data)

    def _popup_ref(self) -> QListWidget | None:
        popup = self._popup
        if popup is None or sip.isdeleted(popup):
            self._popup = None
            return None
        return popup

    def _handle_popup_destroyed(self, *_args: object) -> None:
        self._popup = None

    def _restore_input_focus(self) -> None:
        if sip.isdeleted(self):
            return
        self.setFocus(Qt.FocusReason.OtherFocusReason)

    def _cleanup_filters(self, *_args: object) -> None:
        if self._app is not None:
            self._app.removeEventFilter(self)
