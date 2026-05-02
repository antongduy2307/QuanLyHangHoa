from __future__ import annotations


def scaled(value: int, factor: float) -> int:
    return max(1, int(round(value * factor)))


def scaled_font(value: int, factor: float) -> int:
    scaled_value = scaled(value, factor)
    if abs(factor - 0.85) < 0.001:
        return max(1, int(round(scaled_value * 1.35)))
    return scaled_value
