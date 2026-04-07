from __future__ import annotations

from shared.widgets.common_dialogs import InfoDialog


class SalesDialog(InfoDialog):
    def __init__(self) -> None:
        super().__init__("Sales", "Dialog nghiep vu cho ban hang se duoc them sau.")
