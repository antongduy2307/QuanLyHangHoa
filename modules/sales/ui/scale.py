from __future__ import annotations


def scaled(value: int, factor: float) -> int:
    return max(1, int(round(value * factor)))
