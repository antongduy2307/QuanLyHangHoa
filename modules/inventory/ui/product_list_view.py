from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from modules.inventory.controller import InventoryController
from modules.inventory.dto import InventoryProductDTO
from modules.inventory.ui.inventory_adjustment_dialog import InventoryAdjustmentDialog
from modules.inventory.ui.inventory_receipt_dialog import InventoryReceiptDialog
from modules.inventory.ui.product_dialog import ProductDialog
from shared.widgets.message_box import MessageBox


class ProductListView(QWidget):
    def __init__(self, controller: InventoryController) -> None:
        super().__init__()
        self._controller = controller
        self._products: list[InventoryProductDTO] = []

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("Tim theo ma hoac ten hang...")
        self._search_input.textChanged.connect(self._apply_filter)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Ma hang", "Ten hang", "Kieu don vi", "Ton hien tai"])
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.verticalHeader().setVisible(False)
        self._table.setAlternatingRowColors(True)

        create_button = QPushButton("Tao moi")
        create_button.clicked.connect(self._open_create_product)
        receipt_button = QPushButton("Nhap kho")
        receipt_button.clicked.connect(self._open_receipt_dialog)
        adjustment_button = QPushButton("Dieu chinh kho")
        adjustment_button.clicked.connect(self._open_adjustment_dialog)
        refresh_button = QPushButton("Tai lai")
        refresh_button.clicked.connect(self.reload)

        top_bar = QHBoxLayout()
        top_bar.addWidget(self._search_input, 1)
        top_bar.addWidget(create_button)
        top_bar.addWidget(receipt_button)
        top_bar.addWidget(adjustment_button)
        top_bar.addWidget(refresh_button)

        layout = QVBoxLayout(self)
        title = QLabel("Quan ly hang hoa")
        subtitle = QLabel("Tao hang, nhap kho va dieu chinh kho thong qua service layer hien co.")
        subtitle.setProperty("class", "muted")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addLayout(top_bar)
        layout.addWidget(self._table)

        self.reload()

    def reload(self) -> None:
        try:
            self._products = list(self._controller.list_products())
            self._apply_filter()
        except Exception as exc:
            MessageBox.error(self, "Loi tai du lieu", str(exc))

    def _apply_filter(self) -> None:
        query = self._search_input.text().strip().lower()
        if not query:
            filtered = self._products
        else:
            code_matches = [p for p in self._products if query in p.product_code_base.lower()]
            if code_matches:
                filtered = code_matches
            else:
                filtered = [p for p in self._products if query in p.product_name.lower()]
        self._render_rows(filtered)

    def _render_rows(self, products: list[InventoryProductDTO]) -> None:
        self._table.setRowCount(len(products))
        for row_index, product in enumerate(products):
            self._table.setItem(row_index, 0, QTableWidgetItem(product.product_code_base))
            self._table.setItem(row_index, 1, QTableWidgetItem(product.product_name))
            self._table.setItem(row_index, 2, QTableWidgetItem(product.unit_mode))
            self._table.setItem(row_index, 3, QTableWidgetItem(self._format_balance(product.on_hand_display)))

    def _open_create_product(self) -> None:
        dialog = ProductDialog(self)
        if dialog.exec():
            try:
                payload = dialog.payload()
                self._controller.create_product(**payload)
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Khong tao duoc hang hoa", str(exc))

    def _open_receipt_dialog(self) -> None:
        dialog = InventoryReceiptDialog(self._controller.list_product_options(), self)
        if dialog.exec():
            try:
                self._controller.create_receipt(dialog.payload())
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Khong tao duoc phieu nhap", str(exc))

    def _open_adjustment_dialog(self) -> None:
        dialog = InventoryAdjustmentDialog(self._controller.list_product_options(), self)
        if dialog.exec():
            try:
                self._controller.create_adjustment(dialog.payload())
                self.reload()
            except Exception as exc:
                MessageBox.error(self, "Khong tao duoc phieu dieu chinh", str(exc))

    def _format_balance(self, raw_display: str) -> str:
        if raw_display.endswith("bao"):
            number = raw_display.removesuffix(" bao").strip()
            try:
                decimal_value = Decimal(number).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                return f"{decimal_value} bao"
            except Exception:
                return raw_display
        return raw_display
