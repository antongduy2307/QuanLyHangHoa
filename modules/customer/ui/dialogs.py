from __future__ import annotations

from shared.widgets.common_dialogs import InfoDialog


class CustomerDialog(InfoDialog):
    def __init__(self) -> None:
        super().__init__("Customer", "Dialog chi tiet khach hang se duoc bo sung sau.")
