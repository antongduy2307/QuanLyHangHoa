from __future__ import annotations



def coalesce(value: str | None, default: str = "-") -> str:
    return value.strip() if value and value.strip() else default
