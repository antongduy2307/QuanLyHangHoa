from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppPalette:
    background: str = "#f5f7fb"
    surface: str = "#ffffff"
    surface_alt: str = "#e8eef7"
    text: str = "#1f2933"
    text_muted: str = "#52606d"
    accent: str = "#14532d"
    accent_soft: str = "#d1fae5"
    border: str = "#cbd5e1"


PALETTE = AppPalette()
