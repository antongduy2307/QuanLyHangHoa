from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from types import TracebackType
from unittest.mock import patch

from sqlalchemy import inspect

import core.config
import core.db


class TempMainDbRuntime:
    """Context manager for tests that construct real DB-backed app UI."""

    def __init__(self, *, prefix: str = "quanly-test-runtime-") -> None:
        self._prefix = prefix
        self._tmp_dir: tempfile.TemporaryDirectory[str] | None = None
        self.root: Path | None = None
        self.settings = None
        self._env_patch = None

    def __enter__(self) -> "TempMainDbRuntime":
        self._tmp_dir = tempfile.TemporaryDirectory(prefix=self._prefix)
        self.root = Path(self._tmp_dir.name)
        env = {
            "APP_NAME": "QuanLyHangHoaTest",
            "APP_DB_PATH": str(self.root / "appdata" / "app.db"),
            "APP_LOG_DIR": str(self.root / "appdata" / "logs"),
            "APP_EXPORT_DIR": str(self.root / "appdata" / "exports"),
            "APP_BACKUP_DIR": str(self.root / "appdata" / "backups"),
            "APP_TEMP_DIR": str(self.root / "appdata" / "temp"),
            "APP_UPDATE_MANIFEST_URL": "https://example.com/version.json",
            "APP_UPDATE_TIMEOUT_MS": "1000",
            "APP_UPDATE_DOWNLOAD_TIMEOUT_MS": "1000",
            "APP_UPDATE_DOWNLOAD_RETRY_COUNT": "1",
            "APP_UPDATE_STARTUP_DELAY_MS": "60000",
        }
        self._env_patch = patch.dict(os.environ, env, clear=False)
        self._env_patch.start()
        core.config.get_settings.cache_clear()
        core.db.reset_engine_cache()
        core.db.init_db()
        self.settings = core.config.get_settings()
        assert self.settings.db_path.exists()
        assert "invoices" in set(inspect(core.db.ENGINE).get_table_names())
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        root_logger = logging.getLogger()
        for handler in list(root_logger.handlers):
            root_logger.removeHandler(handler)
            handler.close()
        core.db.ENGINE.dispose()
        core.db.reset_engine_cache()
        core.config.get_settings.cache_clear()
        if self._env_patch is not None:
            self._env_patch.stop()
        if self._tmp_dir is not None:
            self._tmp_dir.cleanup()
