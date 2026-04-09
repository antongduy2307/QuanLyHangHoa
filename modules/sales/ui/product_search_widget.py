from __future__ import annotations

from decimal import Decimal

from PyQt6 import sip
from PyQt6.QtCore import QEvent, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import QApplication, QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget

from core.enums import UnitType
from modules.sales.controller import SellableProductOption
from modules.sales.ui.scale import scaled
from shared.widgets.numeric_inputs import SelectAllSpinBox


class ProductSearchWidget(QWidget):
    item_added = pyqtSignal(object)

    def __init__(self, products: list[SellableProductOption], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._products = products
        self._selected_product: SellableProductOption | None = None
        self._app = QApplication.instance()
        self._suggestion_popup: QListWidget | None = QListWidget()
        self._ui_scale = 1.0

        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Tìm theo mã hoặc tên hàng")
        self.search_input.textChanged.connect(self._update_suggestions)
        self.search_input.installEventFilter(self)

        self._suggestion_popup.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self._suggestion_popup.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._suggestion_popup.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._suggestion_popup.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._suggestion_popup.itemClicked.connect(self._select_product)
        self._suggestion_popup.itemActivated.connect(self._select_product)
        self._suggestion_popup.destroyed.connect(self._handle_popup_destroyed)

        if self._app is not None:
            self._app.installEventFilter(self)
        self.destroyed.connect(self._cleanup_filters)

        self.unit_combo = QComboBox()
        self.unit_combo.currentIndexChanged.connect(self._update_price_label)

        self.quantity_input = SelectAllSpinBox()
        self.quantity_input.setRange(0, 999999999)

        self.price_label = QLabel("Giá: -")

        add_button = QPushButton("Thêm")
        add_button.clicked.connect(self._emit_item)
        self._add_button = add_button

        controls = QHBoxLayout()
        controls.setSpacing(12)
        controls.addWidget(self.unit_combo)
        controls.addWidget(self.quantity_input)
        controls.addWidget(self.price_label, 1)
        controls.addWidget(add_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 6)
        layout.setSpacing(12)
        layout.addWidget(self.search_input)
        layout.addLayout(controls)

        self.apply_ui_scale(1.0)
        self._sync_product(None)

    def apply_ui_scale(self, factor: float) -> None:
        self._ui_scale = factor
        self.search_input.setMinimumHeight(scaled(52, factor))
        self.search_input.setStyleSheet(f"font-size: {scaled(18, factor)}px; padding: {scaled(10, factor)}px {scaled(12, factor)}px;")
        popup = self._popup_ref()
        if popup is not None:
            popup.setMaximumHeight(scaled(260, factor))
            popup.setStyleSheet(
                f"QListWidget {{ font-size: {scaled(16, factor)}px; padding: {scaled(6, factor)}px; border: 1px solid #cbd5e1; }}"
                f"QListWidget::item {{ min-height: {scaled(40, factor)}px; padding: {scaled(8, factor)}px {scaled(10, factor)}px; }}"
            )
        self.unit_combo.setMinimumHeight(scaled(50, factor))
        self.unit_combo.setMinimumWidth(scaled(150, factor))
        self.unit_combo.setStyleSheet(f"font-size: {scaled(18, factor)}px; padding: {scaled(8, factor)}px {scaled(12, factor)}px;")
        self.quantity_input.setMinimumHeight(scaled(50, factor))
        self.quantity_input.setMinimumWidth(scaled(150, factor))
        self.quantity_input.setStyleSheet(f"font-size: {scaled(18, factor)}px; padding: {scaled(8, factor)}px {scaled(12, factor)}px;")
        self.price_label.setStyleSheet(f"font-size: {scaled(20, factor)}px; font-weight: 600; padding: {scaled(6, factor)}px {scaled(10, factor)}px;")
        self._add_button.setMinimumHeight(scaled(52, factor))
        self._add_button.setMinimumWidth(scaled(130, factor))
        self._add_button.setStyleSheet(f"font-size: {scaled(18, factor)}px; font-weight: 600; padding: {scaled(10, factor)}px {scaled(18, factor)}px;")
        controls = self.layout().itemAt(1).layout()
        if controls is not None:
            controls.setSpacing(scaled(12, factor))
        self.layout().setSpacing(scaled(12, factor))

    def eventFilter(self, watched: object, event: object) -> bool:
        popup = self._popup_ref()
        if popup is None:
            return super().eventFilter(watched, event)

        if watched is self.search_input and isinstance(event, QKeyEvent):
            if popup.isVisible():
                if event.key() == Qt.Key.Key_Down:
                    self._move_selection(1)
                    return True
                if event.key() == Qt.Key.Key_Up:
                    self._move_selection(-1)
                    return True
                if event.key() in {Qt.Key.Key_Return, Qt.Key.Key_Enter}:
                    self._activate_current_suggestion()
                    return True
                if event.key() == Qt.Key.Key_Escape:
                    self._hide_suggestions()
                    return True
        if watched is self.search_input and isinstance(event, QEvent):
            if event.type() in {QEvent.Type.Move, QEvent.Type.Resize} and popup.isVisible():
                self._position_suggestion_popup()
        if popup.isVisible() and isinstance(event, QMouseEvent) and event.type() == QEvent.Type.MouseButtonPress:
            global_pos = event.globalPosition().toPoint()
            if not self._is_point_inside_search_or_popup(global_pos):
                self._hide_suggestions()
        return super().eventFilter(watched, event)

    def reload_data(self, products: list[SellableProductOption]) -> None:
        previous_product_id = None if self._selected_product is None else self._selected_product.product_id
        self._products = products
        self._selected_product = next((product for product in products if product.product_id == previous_product_id), None)
        self._update_suggestions()
        self._sync_product(self._selected_product)

    def reset(self) -> None:
        self.search_input.clear()
        self.quantity_input.setValue(0)
        self._hide_suggestions()
        self._sync_product(None)

    def _update_suggestions(self) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        query = self.search_input.text().strip().lower()
        popup.clear()
        if not query:
            self._hide_suggestions()
            return
        code_matches = [product for product in self._products if query in product.product_code_base.lower()]
        matches = code_matches if code_matches else [product for product in self._products if query in product.product_name.lower()]
        if not matches:
            self._hide_suggestions()
            return
        for product in matches[:20]:
            item = QListWidgetItem(f"{product.product_code_base} - {product.product_name}")
            item.setData(Qt.ItemDataRole.UserRole, product.product_id)
            popup.addItem(item)
        popup.setCurrentRow(0)
        self._position_suggestion_popup()
        popup.show()
        popup.raise_()

    def _position_suggestion_popup(self) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        popup_width = max(self.search_input.width(), scaled(520, self._ui_scale))
        row_count = min(max(popup.count(), 1), 6)
        row_height = popup.sizeHintForRow(0)
        if row_height <= 0:
            row_height = scaled(40, self._ui_scale)
        frame = popup.frameWidth() * 2
        popup_height = row_count * row_height + frame + 6
        global_pos = self.search_input.mapToGlobal(QPoint(0, self.search_input.height()))
        popup.setGeometry(global_pos.x(), global_pos.y(), popup_width, popup_height)

    def _is_point_inside_search_or_popup(self, global_pos: QPoint) -> bool:
        popup = self._popup_ref()
        if popup is None:
            return False
        search_pos = self.search_input.mapToGlobal(QPoint(0, 0))
        search_rect = self.search_input.rect().translated(search_pos)
        return search_rect.contains(global_pos) or popup.geometry().contains(global_pos)

    def _hide_suggestions(self) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        popup.hide()
        popup.clearSelection()

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

    def _activate_current_suggestion(self) -> None:
        popup = self._popup_ref()
        if popup is None:
            return
        item = popup.currentItem()
        if item is not None:
            self._select_product(item)

    def _select_product(self, item: QListWidgetItem) -> None:
        product_id = item.data(Qt.ItemDataRole.UserRole)
        product = next((candidate for candidate in self._products if candidate.product_id == product_id), None)
        if product is None:
            return
        self._sync_product(product)
        self.search_input.blockSignals(True)
        self.search_input.setText(f"{product.product_code_base} - {product.product_name}")
        self.search_input.blockSignals(False)
        self._hide_suggestions()

    def _sync_product(self, product: SellableProductOption | None) -> None:
        self._selected_product = product
        self.unit_combo.clear()
        if product is None:
            self.unit_combo.setEnabled(False)
            self.quantity_input.setEnabled(False)
            self.price_label.setText("Giá: -")
            return
        for unit_type in product.enabled_prices:
            self.unit_combo.addItem(unit_type.value, unit_type)
        self.unit_combo.setEnabled(True)
        self.quantity_input.setEnabled(True)
        self._update_price_label()

    def _update_price_label(self) -> None:
        if self._selected_product is None:
            self.price_label.setText("Giá: -")
            return
        unit_type = self.unit_combo.currentData()
        if unit_type is None:
            self.price_label.setText("Giá: -")
            return
        price = self._selected_product.enabled_prices[unit_type]
        self.price_label.setText(f"Giá: {price:,.0f}")

    def _emit_item(self) -> None:
        if self._selected_product is None:
            return
        unit_type = self.unit_combo.currentData()
        quantity = Decimal(self.quantity_input.value())
        if unit_type is None or quantity <= Decimal("0"):
            return
        price = self._selected_product.enabled_prices[unit_type]
        self.item_added.emit(
            {
                "product_id": self._selected_product.product_id,
                "product_code_base": self._selected_product.product_code_base,
                "product_name": self._selected_product.product_name,
                "unit_type": unit_type,
                "quantity": quantity,
                "unit_price": price,
                "line_total": quantity * price,
            }
        )
        self.quantity_input.setValue(0)

    def _popup_ref(self) -> QListWidget | None:
        popup = self._suggestion_popup
        if popup is None or sip.isdeleted(popup):
            self._suggestion_popup = None
            return None
        return popup

    def _handle_popup_destroyed(self, *_args: object) -> None:
        self._suggestion_popup = None

    def _cleanup_filters(self, *_args: object) -> None:
        if self._app is not None:
            self._app.removeEventFilter(self)
