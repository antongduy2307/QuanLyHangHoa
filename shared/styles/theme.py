from __future__ import annotations

from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication

from shared.styles.palette import PALETTE


def build_stylesheet() -> str:
    return f"""
    QWidget {{
        background-color: {PALETTE.background};
        color: {PALETTE.text};
        font-family: 'Segoe UI';
        font-size: 13px;
    }}
    QLineEdit,
    QComboBox,
    QDateEdit,
    QAbstractSpinBox,
    QTextEdit,
    QPlainTextEdit {{
        background: {PALETTE.surface};
        color: {PALETTE.text};
        border: 1px solid #d8dfe7;
        border-radius: 8px;
        padding: 8px 12px;
        selection-background-color: #eaded2;
    }}
    QLineEdit:focus,
    QComboBox:focus,
    QDateEdit:focus,
    QAbstractSpinBox:focus,
    QTextEdit:focus,
    QPlainTextEdit:focus {{
        border: 1px solid {PALETTE.accent};
    }}
    QComboBox {{
        padding-right: 28px;
    }}
    QComboBox::drop-down,
    QDateEdit::drop-down,
    QAbstractSpinBox::drop-down {{
        subcontrol-origin: padding;
        subcontrol-position: top right;
        width: 24px;
        border: none;
        background: transparent;
    }}
    QComboBox::down-arrow,
    QDateEdit::down-arrow,
    QAbstractSpinBox::down-arrow {{
        width: 9px;
        height: 9px;
        margin-right: 8px;
    }}
    QMainWindow, QFrame#pageCard {{
        background-color: {PALETTE.surface};
    }}
    QTabWidget::pane {{
        border: 1px solid {PALETTE.border};
        background: {PALETTE.surface};
        border-radius: 8px;
        margin-top: 8px;
    }}
    QTabBar::tab {{
        background: {PALETTE.surface_alt};
        color: {PALETTE.text};
        padding: 10px 16px;
        margin-right: 4px;
        border-top-left-radius: 8px;
        border-top-right-radius: 8px;
        border: 1px solid #e1d5c9;
        border-bottom: none;
    }}
    QTabBar::tab:selected {{
        background: {PALETTE.accent_soft};
        color: {PALETTE.accent_strong};
        border-color: {PALETTE.accent};
    }}
    QTableWidget,
    QTableView {{
        background: {PALETTE.surface};
        border: 1px solid #d8dfe7;
        border-radius: 10px;
        gridline-color: #eef2f7;
        alternate-background-color: #faf7f3;
        selection-background-color: #eaded2;
        selection-color: {PALETTE.text};
        outline: none;
    }}
    QHeaderView::section {{
        background: {PALETTE.surface_alt};
        color: #5f4a3a;
        border: none;
        border-bottom: 1px solid #e1d5c9;
        border-right: 1px solid #efe6de;
        padding: 8px 8px;
        font-weight: 600;
    }}
    QPushButton {{
        background: transparent;
        color: {PALETTE.accent};
        border: 1px solid {PALETTE.accent};
        border-radius: 8px;
        padding: 8px 14px;
        font-weight: 600;
    }}
    QPushButton:hover {{
        background: {PALETTE.accent_soft};
    }}
    QPushButton:pressed {{
        background: #eadbce;
        border-color: {PALETTE.accent_strong};
        color: {PALETTE.accent_strong};
    }}
    QPushButton:disabled {{
        color: {PALETTE.text_muted};
        border-color: {PALETTE.border};
        background: {PALETTE.surface_alt};
    }}
    QLabel[class='muted'] {{
        color: {PALETTE.text_muted};
    }}
    """


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(PALETTE.background))
    palette.setColor(QPalette.ColorRole.Base, QColor(PALETTE.surface))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor("#faf7f3"))
    palette.setColor(QPalette.ColorRole.Button, QColor(PALETTE.surface))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(PALETTE.accent))
    palette.setColor(QPalette.ColorRole.Text, QColor(PALETTE.text))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(PALETTE.text))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#eaded2"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(PALETTE.text))
    app.setPalette(palette)
    app.setStyleSheet(build_stylesheet())
