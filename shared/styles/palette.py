from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AppPalette:
    background: str = "#f5f7fb"
    surface: str = "#ffffff"
    surface_alt: str = "#f2ece6"
    text: str = "#1f2933"
    text_muted: str = "#52606d"
    accent: str = "#8b5e3c"
    accent_soft: str = "#f4eadf"
    accent_strong: str = "#6f4628"
    border: str = "#cbd5e1"


PALETTE = AppPalette()
