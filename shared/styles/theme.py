from __future__ import annotations

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
    }}
    QTabBar::tab:selected {{
        background: {PALETTE.accent};
        color: white;
    }}
    QPushButton {{
        background: {PALETTE.accent};
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 14px;
    }}
    QLabel[class='muted'] {{
        color: {PALETTE.text_muted};
    }}
    """



def apply_theme(app: QApplication) -> None:
    app.setStyleSheet(build_stylesheet())
