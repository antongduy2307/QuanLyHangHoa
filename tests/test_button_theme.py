from __future__ import annotations

import unittest

from shared.styles.palette import PALETTE
from shared.styles.theme import build_stylesheet


class ButtonThemeTestCase(unittest.TestCase):
    def test_buttons_use_outline_brown_theme(self) -> None:
        stylesheet = build_stylesheet()
        self.assertIn("background: transparent;", stylesheet)
        self.assertIn(f"color: {PALETTE.accent};", stylesheet)
        self.assertIn(f"border: 1px solid {PALETTE.accent};", stylesheet)
        self.assertIn(f"background: {PALETTE.accent_soft};", stylesheet)


if __name__ == "__main__":
    unittest.main()
