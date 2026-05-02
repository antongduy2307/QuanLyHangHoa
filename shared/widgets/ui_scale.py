from __future__ import annotations

from PyQt6.QtWidgets import QLayout, QTableView, QTableWidget, QWidget


_MANAGED_STYLE_START = "/* codex-ui-scale:start */"
_MANAGED_STYLE_END = "/* codex-ui-scale:end */"
_BASE_LABEL_FONT = 18
_BASE_BUTTON_FONT = 18
_BASE_BUTTON_MIN_HEIGHT = 48
_BASE_BUTTON_PADDING_VERTICAL = 10
_BASE_BUTTON_PADDING_HORIZONTAL = 16
_BASE_INPUT_FONT = 18
_BASE_INPUT_MIN_HEIGHT = 46
_BASE_INPUT_PADDING_VERTICAL = 8
_BASE_INPUT_PADDING_HORIZONTAL = 10
_BASE_CHECKBOX_FONT = 18
_BASE_CHECKBOX_SPACING = 10
_BASE_CHECKBOX_PADDING = 4
_BASE_TABLE_FONT = 18
_BASE_HEADER_FONT = 17
_BASE_HEADER_PADDING_VERTICAL = 10
_BASE_HEADER_PADDING_HORIZONTAL = 8
_BASE_HEADER_MIN_HEIGHT = 44
_BASE_TAB_FONT = 18
_BASE_TAB_MIN_HEIGHT = 42
_BASE_TAB_MIN_WIDTH = 140
_BASE_TAB_PADDING_VERTICAL = 10
_BASE_TAB_PADDING_HORIZONTAL = 18
_BASE_LAYOUT_SPACING = 14
_BASE_LAYOUT_MARGIN = 16
_BASE_TABLE_ROW_HEIGHT = 52
_BASE_TABLE_HEADER_HEIGHT = 44
_STANDARD_FONT_MULTIPLIER = 1.35


def apply_large_ui(widget: QWidget, preset: str | None = None) -> None:
    from modules.settings.service import get_ui_scale_factor, get_ui_scale_preset

    factor = get_ui_scale_factor(preset or get_ui_scale_preset())
    existing = _strip_managed_styles(widget.styleSheet())
    widget.setStyleSheet(_compose_stylesheet(existing, factor))

    layout = widget.layout()
    if layout is not None:
        _apply_layout_scale(layout, factor)
    for table in widget.findChildren(QTableWidget):
        _apply_table_scale(table, factor)
    for table in widget.findChildren(QTableView):
        _apply_table_scale(table, factor)


def _compose_stylesheet(existing: str, factor: float) -> str:
    managed_block = "\n".join(
        [
            _MANAGED_STYLE_START,
            "QLabel {",
            f"    font-size: {_font_scaled(_BASE_LABEL_FONT, factor)}px;",
            "}",
            "QPushButton {",
            f"    font-size: {_font_scaled(_BASE_BUTTON_FONT, factor)}px;",
            f"    min-height: {_scaled(_BASE_BUTTON_MIN_HEIGHT, factor)}px;",
            f"    padding: {_scaled(_BASE_BUTTON_PADDING_VERTICAL, factor)}px {_scaled(_BASE_BUTTON_PADDING_HORIZONTAL, factor)}px;",
            "}",
            "QLineEdit,",
            "QComboBox,",
            "QDateEdit,",
            "QAbstractSpinBox {",
            f"    font-size: {_font_scaled(_BASE_INPUT_FONT, factor)}px;",
            f"    min-height: {_scaled(_BASE_INPUT_MIN_HEIGHT, factor)}px;",
            f"    padding: {_scaled(_BASE_INPUT_PADDING_VERTICAL, factor)}px {_scaled(_BASE_INPUT_PADDING_HORIZONTAL, factor)}px;",
            "}",
            "QCheckBox,",
            "QRadioButton {",
            f"    font-size: {_font_scaled(_BASE_CHECKBOX_FONT, factor)}px;",
            f"    spacing: {_scaled(_BASE_CHECKBOX_SPACING, factor)}px;",
            f"    padding: {_scaled(_BASE_CHECKBOX_PADDING, factor)}px {_scaled(_BASE_CHECKBOX_PADDING, factor)}px;",
            "}",
            "QTableWidget,",
            "QTableView {",
            f"    font-size: {_font_scaled(_BASE_TABLE_FONT, factor)}px;",
            "}",
            "QHeaderView::section {",
            f"    font-size: {_font_scaled(_BASE_HEADER_FONT, factor)}px;",
            f"    padding: {_scaled(_BASE_HEADER_PADDING_VERTICAL, factor)}px {_scaled(_BASE_HEADER_PADDING_HORIZONTAL, factor)}px;",
            f"    min-height: {_scaled(_BASE_HEADER_MIN_HEIGHT, factor)}px;",
            "}",
            "QTabBar::tab {",
            f"    font-size: {_font_scaled(_BASE_TAB_FONT, factor)}px;",
            f"    min-height: {_scaled(_BASE_TAB_MIN_HEIGHT, factor)}px;",
            f"    min-width: {_scaled(_BASE_TAB_MIN_WIDTH, factor)}px;",
            f"    padding: {_scaled(_BASE_TAB_PADDING_VERTICAL, factor)}px {_scaled(_BASE_TAB_PADDING_HORIZONTAL, factor)}px;",
            "}",
            _MANAGED_STYLE_END,
        ]
    ).strip()
    return "\n".join(part for part in [existing.strip(), managed_block] if part).strip()


def _strip_managed_styles(stylesheet: str) -> str:
    start = stylesheet.find(_MANAGED_STYLE_START)
    end = stylesheet.find(_MANAGED_STYLE_END)
    if start < 0 or end < 0 or end < start:
        return stylesheet.strip()
    return (stylesheet[:start] + stylesheet[end + len(_MANAGED_STYLE_END):]).strip()


def _apply_layout_scale(layout: QLayout, factor: float) -> None:
    _remember_layout_baseline(layout)
    layout.setSpacing(_scaled(_layout_baseline(layout, "spacing", _BASE_LAYOUT_SPACING), factor))
    layout.setContentsMargins(
        _scaled(_layout_baseline(layout, "margin_left", _BASE_LAYOUT_MARGIN), factor),
        _scaled(_layout_baseline(layout, "margin_top", _BASE_LAYOUT_MARGIN), factor),
        _scaled(_layout_baseline(layout, "margin_right", _BASE_LAYOUT_MARGIN), factor),
        _scaled(_layout_baseline(layout, "margin_bottom", _BASE_LAYOUT_MARGIN), factor),
    )
    for index in range(layout.count()):
        child_layout = layout.itemAt(index).layout()
        if child_layout is not None:
            _apply_layout_scale(child_layout, factor)


def _remember_layout_baseline(layout: QLayout) -> None:
    if layout.property("ui_scale_spacing_base") is None:
        spacing = layout.spacing()
        layout.setProperty("ui_scale_spacing_base", max(spacing, _BASE_LAYOUT_SPACING))
        margins = layout.contentsMargins()
        layout.setProperty("ui_scale_margin_left_base", max(margins.left(), _BASE_LAYOUT_MARGIN))
        layout.setProperty("ui_scale_margin_top_base", max(margins.top(), _BASE_LAYOUT_MARGIN))
        layout.setProperty("ui_scale_margin_right_base", max(margins.right(), _BASE_LAYOUT_MARGIN))
        layout.setProperty("ui_scale_margin_bottom_base", max(margins.bottom(), _BASE_LAYOUT_MARGIN))


def _layout_baseline(layout: QLayout, key: str, fallback: int) -> int:
    value = layout.property(f"ui_scale_{key}_base")
    return int(value) if value is not None else fallback


def _apply_table_scale(table: QTableWidget | QTableView, factor: float) -> None:
    _remember_table_baseline(table)
    table.verticalHeader().setDefaultSectionSize(_scaled(_table_baseline(table, "row_height", _BASE_TABLE_ROW_HEIGHT), factor))
    table.verticalHeader().setMinimumSectionSize(_scaled(_table_baseline(table, "row_height", _BASE_TABLE_ROW_HEIGHT), factor))
    table.horizontalHeader().setMinimumHeight(_scaled(_table_baseline(table, "header_height", _BASE_TABLE_HEADER_HEIGHT), factor))


def _remember_table_baseline(table: QTableWidget | QTableView) -> None:
    if table.property("ui_scale_row_height_base") is None:
        row_height = max(table.verticalHeader().defaultSectionSize(), table.verticalHeader().minimumSectionSize(), _BASE_TABLE_ROW_HEIGHT)
        header_height = max(table.horizontalHeader().minimumHeight(), _BASE_TABLE_HEADER_HEIGHT)
        table.setProperty("ui_scale_row_height_base", row_height)
        table.setProperty("ui_scale_header_height_base", header_height)


def _table_baseline(table: QTableWidget | QTableView, key: str, fallback: int) -> int:
    value = table.property(f"ui_scale_{key}_base")
    return int(value) if value is not None else fallback


def _scaled(value: int, factor: float) -> int:
    return max(1, int(round(value * factor)))


def _font_scaled(value: int, factor: float) -> int:
    scaled_value = _scaled(value, factor)
    if _is_standard_factor(factor):
        return max(1, int(round(scaled_value * _STANDARD_FONT_MULTIPLIER)))
    return scaled_value


def _is_standard_factor(factor: float) -> bool:
    return abs(factor - 0.85) < 0.001


def boost_font_size(value: int, preset: str | None = None) -> int:
    from modules.settings.service import get_ui_scale_preset

    effective_preset = preset or get_ui_scale_preset()
    if effective_preset == "standard":
        return max(1, int(round(value * _STANDARD_FONT_MULTIPLIER)))
    return value
