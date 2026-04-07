from __future__ import annotations

import logging as std_logging



def configure_logging(level: str = "INFO") -> None:
    std_logging.basicConfig(
        level=getattr(std_logging, level.upper(), std_logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )



def get_logger(name: str) -> std_logging.Logger:
    return std_logging.getLogger(name)
