from __future__ import annotations

from shared.widgets.common_dialogs import InfoDialog


class ReturnsDialog(InfoDialog):
    def __init__(self) -> None:
        super().__init__("Returns", "Dialog cho module tra hang se duoc hoan thien sau.")
