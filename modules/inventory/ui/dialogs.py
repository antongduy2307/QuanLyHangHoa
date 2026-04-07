from __future__ import annotations

from shared.widgets.common_dialogs import InfoDialog


class InventoryDialog(InfoDialog):
    def __init__(self) -> None:
        super().__init__("Hàng hóa", "Hộp thoại nghiệp vụ cho hàng hóa sẽ được bổ sung sau.")
