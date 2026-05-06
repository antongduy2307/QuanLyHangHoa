from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from core.config import Settings, get_settings
from core.logging import get_logger
from modules.attendance.db import get_attendance_db_path


LOGGER = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class BackupResult:
    output_path: Path
    included_files: list[str]
    missing_files: list[str]
    created_at: str
    warnings: list[str]


class UserBackupService:
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def create_user_backup(self) -> BackupResult:
        now = datetime.now()
        created_at = now.isoformat(timespec="seconds")
        timestamp = now.strftime("%Y%m%d-%H%M%S")
        backup_dir = self._settings.backup_dir
        backup_dir.mkdir(parents=True, exist_ok=True)
        output_path = self._next_backup_path(backup_dir, timestamp)

        app_db_path = self._settings.db_path
        attendance_db_path = get_attendance_db_path()
        included_files: list[str] = []
        missing_files: list[str] = []
        warnings: list[str] = []

        app_db_present = app_db_path.exists()
        attendance_db_present = attendance_db_path.exists()

        if not app_db_present:
            missing_files.append("app.db")
            warnings.append(f"Main database file is missing: {app_db_path}")
        if not attendance_db_present:
            missing_files.append("attendance.db")

        with ZipFile(output_path, "w", compression=ZIP_DEFLATED) as archive:
            if app_db_present:
                archive.write(app_db_path, "app.db")
                included_files.append("app.db")
            if attendance_db_present:
                archive.write(attendance_db_path, "attendance.db")
                included_files.append("attendance.db")

            manifest = {
                "created_at": created_at,
                "app_db_present": app_db_present,
                "attendance_db_present": attendance_db_present,
                "included_files": included_files,
                "missing_files": missing_files,
                "app_db_source_path": str(app_db_path),
                "attendance_db_source_path": str(attendance_db_path),
                "warnings": warnings,
            }
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))

        LOGGER.info(
            "User backup created at %s | included=%s | missing=%s | warnings=%s",
            output_path,
            included_files,
            missing_files,
            len(warnings),
        )
        return BackupResult(
            output_path=output_path,
            included_files=included_files,
            missing_files=missing_files,
            created_at=created_at,
            warnings=warnings,
        )

    def _next_backup_path(self, backup_dir: Path, timestamp: str) -> Path:
        candidate = backup_dir / f"backup-{timestamp}.zip"
        if not candidate.exists():
            return candidate
        index = 2
        while True:
            candidate = backup_dir / f"backup-{timestamp}-{index}.zip"
            if not candidate.exists():
                return candidate
            index += 1
