from __future__ import annotations

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLineEdit, QMessageBox, QVBoxLayout

from core.exceptions import ValidationError


class CustomerDialog(QDialog):
    def __init__(
        self,
        *,
        title: str,
        customer_name: str = "",
        phone: str | None = None,
        parent: QDialog | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(360, 180)

        self.name_input = QLineEdit(customer_name)
        self.phone_input = QLineEdit(phone or "")

        form_layout = QFormLayout()
        form_layout.addRow("Ten khach", self.name_input)
        form_layout.addRow("Dien thoai", self.phone_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._handle_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form_layout)
        layout.addWidget(buttons)

    def payload(self) -> dict[str, str | None]:
        return {
            "customer_name": self.name_input.text(),
            "phone": self.phone_input.text() or None,
        }

    def _handle_accept(self) -> None:
        if not self.name_input.text().strip():
            QMessageBox.critical(self, "Loi du lieu", "Ten khach hang khong duoc de trong.")
            return
        if not self.phone_input.text().strip():
            QMessageBox.warning(self, "Canh bao", "Khach hang nay khong co so dien thoai.")
        self.accept()
