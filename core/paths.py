from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
DEFAULT_DB_PATH = DATA_DIR / "app.db"
DEFAULT_EXPORT_DIR = DATA_DIR / "exports"
DEFAULT_BACKUP_DIR = DATA_DIR / "backups"
DEFAULT_TEMP_DIR = DATA_DIR / "temp"
