from __future__ import annotations

from pathlib import Path
from typing import Iterable



def ensure_directories(paths: Iterable[Path]) -> None:
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)
