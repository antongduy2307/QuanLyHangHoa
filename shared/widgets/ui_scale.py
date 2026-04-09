from __future__ import annotations

from PyQt6.QtWidgets import QLayout, QTableView, QTableWidget, QWidget


_LARGE_UI_STYLES = """
QLabel {
    font-size: 18px;
}
QPushButton {
    font-size: 18px;
    min-height: 48px;
    padding: 10px 16px;
}
QLineEdit,
QComboBox,
QDateEdit,
QAbstractSpinBox {
    font-size: 18px;
    min-height: 46px;
    padding: 8px 10px;
}
QCheckBox,
QRadioButton {
    font-size: 18px;
    spacing: 10px;
    padding: 4px 4px;
}
QTableWidget,
QTableView {
    font-size: 18px;
}
QHeaderView::section {
    font-size: 17px;
    padding: 10px 8px;
    min-height: 44px;
}
QTabBar::tab {
    font-size: 18px;
    min-height: 42px;
    min-width: 140px;
    padding: 10px 18px;
}
"""


def apply_large_ui(widget: QWidget) -> None:
    existing = widget.styleSheet().strip()
    if _LARGE_UI_STYLES.strip() not in existing:
        widget.setStyleSheet((existing + "\n" + _LARGE_UI_STYLES).strip())
    layout = widget.layout()
    if layout is not None:
        _enlarge_layout(layout)
    for table in widget.findChildren(QTableWidget):
        _enlarge_table(table)
    for table in widget.findChildren(QTableView):
        _enlarge_table(table)


def _enlarge_layout(layout: QLayout) -> None:
    if layout.spacing() < 14:
        layout.setSpacing(14)
    margins = layout.contentsMargins()
    layout.setContentsMargins(
        max(margins.left(), 16),
        max(margins.top(), 16),
        max(margins.right(), 16),
        max(margins.bottom(), 16),
    )
    for index in range(layout.count()):
        child_layout = layout.itemAt(index).layout()
        if child_layout is not None:
            _enlarge_layout(child_layout)


def _enlarge_table(table: QTableWidget | QTableView) -> None:
    table.verticalHeader().setDefaultSectionSize(max(table.verticalHeader().defaultSectionSize(), 52))
    table.verticalHeader().setMinimumSectionSize(max(table.verticalHeader().minimumSectionSize(), 52))
    table.horizontalHeader().setMinimumHeight(max(table.horizontalHeader().minimumHeight(), 44))
