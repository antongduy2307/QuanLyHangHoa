from __future__ import annotations

from shared.widgets.common_dialogs import InfoDialog


class ReturnsDialog(InfoDialog):
    def __init__(self) -> None:
        super().__init__("Trả hàng", "Hộp thoại cho module trả hàng sẽ được hoàn thiện sau")
