from __future__ import annotations

from shared.widgets.common_dialogs import InfoDialog


class InventoryDialog(InfoDialog):
    def __init__(self) -> None:
        super().__init__("Inventory", "Dialog nghiep vu cho inventory se duoc bo sung sau.")
