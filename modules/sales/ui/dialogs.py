from __future__ import annotations

from shared.widgets.common_dialogs import InfoDialog


class SalesDialog(InfoDialog):
    def __init__(self) -> None:
        super().__init__("Bán hàng", "Hộp thoại nghiệp vụ cho bán hàng sẽ được thêm sau.")
