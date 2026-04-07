from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from modules.inventory.service import InventoryService
from modules.inventory.ui.dialogs import InventoryDialog
from modules.inventory.ui.forms import InventoryFilterForm
from modules.inventory.ui.widgets import InventoryTable


class InventoryPage(QWidget):
    def __init__(self, service: InventoryService) -> None:
        super().__init__()
        self._service = service
        self._table = InventoryTable()
        self._status_label = QLabel()
        self._status_label.setProperty("class", "muted")

        layout = QVBoxLayout(self)
        title = QLabel("Module Hang hoa")
        subtitle = QLabel("Schema da tach thanh Product, ProductPrice, InventoryBalance, Receipt va Adjustment. UI van chi doc service.")
        subtitle.setWordWrap(True)
        subtitle.setProperty("class", "muted")

        refresh_button = QPushButton("Tai lai du lieu")
        refresh_button.clicked.connect(self.refresh)
        dialog_button = QPushButton("Mo dialog mau")
        dialog_button.clicked.connect(self.open_dialog)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addWidget(self._status_label)
        layout.addWidget(InventoryFilterForm())
        layout.addWidget(refresh_button)
        layout.addWidget(dialog_button)
        layout.addWidget(self._table)

        self.refresh()

    def refresh(self) -> None:
        products = list(self._service.list_products())
        self._table.set_items(products)
        self._status_label.setText(f"San sang. Co {len(products)} product trong SQLite local.")

    def open_dialog(self) -> None:
        InventoryDialog().exec()
