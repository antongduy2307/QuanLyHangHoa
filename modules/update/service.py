from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

from PyQt6.QtCore import QObject, QProcess, QTimer, QUrl, pyqtSignal
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from core.config import Settings, get_settings
from core.logging import get_logger
from core.paths import sanitize_app_dir_name
from core.utils import ensure_directories
from core.version import APP_VERSION


LOGGER = get_logger(__name__)
_ALLOWED_URL_SCHEMES = {"http", "https"}
_TIMEOUT_PROPERTY = "updateTimedOut"
_WRITE_ERROR_PROPERTY = "updateWriteError"
_INSTALLER_ARGS: tuple[str, ...] = ("/NORESTART",)


@dataclass(frozen=True, slots=True)
class UpdateManifest:
    version: str
    installer_url: str
    notes: tuple[str, ...]
    min_required_version: str


@dataclass(frozen=True, slots=True)
class UpdateCheckResult:
    has_update: bool
    current_version: str
    latest_version: str | None = None
    installer_url: str | None = None
    notes: tuple[str, ...] = ()
    min_required_version: str | None = None
    is_forced_update: bool = False
    error: str | None = None
    manifest_url: str | None = None


@dataclass(frozen=True, slots=True)
class UpdateDownloadResult:
    success: bool
    version: str
    installer_url: str
    installer_path: Path | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class _PendingDownload:
    partial_path: Path
    final_path: Path
    version: str
    installer_url: str


def compare_versions(left: str, right: str) -> int:
    left_parts = _normalize_version(left)
    right_parts = _normalize_version(right)
    max_length = max(len(left_parts), len(right_parts))
    padded_left = left_parts + (0,) * (max_length - len(left_parts))
    padded_right = right_parts + (0,) * (max_length - len(right_parts))
    if padded_left < padded_right:
        return -1
    if padded_left > padded_right:
        return 1
    return 0


def parse_update_manifest(payload: bytes) -> UpdateManifest:
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Manifest cập nhật không phải JSON hợp lệ.") from exc

    if not isinstance(data, dict):
        raise ValueError("Manifest cập nhật phải là một object JSON.")

    version = _require_string_field(data, "version")
    installer_url = _require_string_field(data, "installer_url")
    min_required_version = _require_string_field(data, "min_required_version")
    notes_value = data.get("notes")
    if not isinstance(notes_value, list) or any(not isinstance(item, str) or not item.strip() for item in notes_value):
        raise ValueError("Manifest cập nhật có trường notes không hợp lệ.")
    notes = tuple(item.strip() for item in notes_value)

    _normalize_version(version)
    _normalize_version(min_required_version)
    if not _is_supported_url(installer_url):
        raise ValueError("Manifest cập nhật có installer_url không hợp lệ.")

    return UpdateManifest(
        version=version.strip(),
        installer_url=installer_url.strip(),
        notes=notes,
        min_required_version=min_required_version.strip(),
    )


def build_update_check_result(
    manifest: UpdateManifest,
    *,
    current_version: str,
    manifest_url: str | None = None,
) -> UpdateCheckResult:
    is_forced_update = compare_versions(current_version, manifest.min_required_version) < 0
    has_update = compare_versions(manifest.version, current_version) > 0 or is_forced_update
    return UpdateCheckResult(
        has_update=has_update,
        current_version=current_version,
        latest_version=manifest.version,
        installer_url=manifest.installer_url,
        notes=manifest.notes,
        min_required_version=manifest.min_required_version,
        is_forced_update=is_forced_update,
        manifest_url=manifest_url,
    )


class UpdateService(QObject):
    check_finished = pyqtSignal(object)
    download_finished = pyqtSignal(object)
    download_progress = pyqtSignal(int, int)

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        current_version: str = APP_VERSION,
        manifest_url: str | None = None,
        timeout_ms: int | None = None,
        network_manager: QNetworkAccessManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings or get_settings()
        self._current_version = current_version
        self._manifest_url = manifest_url or self._settings.update_manifest_url
        self._timeout_ms = timeout_ms or self._settings.update_check_timeout_ms
        self._network = network_manager or QNetworkAccessManager(self)
        self._timers: dict[object, QTimer] = {}
        self._downloads: dict[object, _PendingDownload] = {}

    def check_for_update(self, manifest_url: str | None = None) -> None:
        target_url = (manifest_url or self._manifest_url).strip()
        if not _is_supported_url(target_url):
            self.check_finished.emit(
                UpdateCheckResult(
                    has_update=False,
                    current_version=self._current_version,
                    error="URL manifest cập nhật không hợp lệ.",
                    manifest_url=target_url or None,
                )
            )
            return

        request = QNetworkRequest(QUrl(target_url))
        reply = self._network.get(request)
        self._attach_timeout(reply)
        reply.finished.connect(lambda: self._handle_check_finished(reply, target_url))

    def download_installer(self, installer_url: str, version: str) -> None:
        target_url = installer_url.strip()
        if not _is_supported_url(target_url):
            self.download_finished.emit(
                UpdateDownloadResult(
                    success=False,
                    version=version,
                    installer_url=installer_url,
                    error="Installer URL không hợp lệ.",
                )
            )
            return

        ensure_directories([self._settings.temp_dir])
        installer_name = self.build_installer_filename(target_url, version)
        final_path = self._settings.temp_dir / installer_name
        partial_path = final_path.with_suffix(f"{final_path.suffix}.download")
        final_path.unlink(missing_ok=True)
        partial_path.unlink(missing_ok=True)

        request = QNetworkRequest(QUrl(target_url))
        reply = self._network.get(request)
        self._downloads[reply] = _PendingDownload(
            partial_path=partial_path,
            final_path=final_path,
            version=version,
            installer_url=target_url,
        )
        self._attach_timeout(reply)
        reply.readyRead.connect(lambda: self._handle_download_ready_read(reply))
        reply.downloadProgress.connect(self.download_progress.emit)
        reply.finished.connect(lambda: self._handle_download_finished(reply))

    def build_installer_filename(self, installer_url: str, version: str) -> str:
        file_name = PurePosixPath(urlparse(installer_url).path).name
        if file_name and file_name.lower().endswith(".exe"):
            return file_name
        app_dir_name = sanitize_app_dir_name(self._settings.app_name)
        return f"{app_dir_name}-Setup-{version}.exe"

    def create_launcher_script(self, installer_path: Path, *, wait_for_pid: int | None = None) -> Path:
        ensure_directories([self._settings.temp_dir])
        launcher_path = self._settings.temp_dir / f"launch-update-{installer_path.stem}.cmd"
        launcher_path.write_text(
            self._build_launcher_script(installer_path, wait_for_pid=wait_for_pid or os.getpid()),
            encoding="utf-8",
        )
        return launcher_path

    def launch_installer_after_exit(self, installer_path: Path, *, wait_for_pid: int | None = None) -> Path:
        launcher_path = self.create_launcher_script(installer_path, wait_for_pid=wait_for_pid)
        command = os.environ.get("COMSPEC", "cmd.exe")
        started = QProcess.startDetached(command, ["/c", str(launcher_path)])
        if not started:
            raise RuntimeError("Không thể khởi chạy launcher cập nhật.")
        return launcher_path

    def _handle_check_finished(self, reply: object, manifest_url: str) -> None:
        if self._has_network_error(reply):
            error = self._reply_error_message(reply, "kiểm tra cập nhật")
            self._cleanup_reply(reply)
            self.check_finished.emit(
                UpdateCheckResult(
                    has_update=False,
                    current_version=self._current_version,
                    error=error,
                    manifest_url=manifest_url,
                )
            )
            return

        try:
            manifest = parse_update_manifest(_read_reply_bytes(reply))
            result = build_update_check_result(
                manifest,
                current_version=self._current_version,
                manifest_url=manifest_url,
            )
        except ValueError as exc:
            LOGGER.warning("Update manifest không hợp lệ từ %s: %s", manifest_url, exc)
            result = UpdateCheckResult(
                has_update=False,
                current_version=self._current_version,
                error=str(exc),
                manifest_url=manifest_url,
            )
        finally:
            self._cleanup_reply(reply)

        self.check_finished.emit(result)

    def _handle_download_ready_read(self, reply: object) -> None:
        pending = self._downloads.get(reply)
        if pending is None:
            return

        chunk = _read_reply_bytes(reply)
        if not chunk:
            return

        try:
            ensure_directories([pending.partial_path.parent])
            with pending.partial_path.open("ab") as handle:
                handle.write(chunk)
        except OSError as exc:
            LOGGER.exception("Không thể ghi installer cập nhật vào %s", pending.partial_path)
            reply.setProperty(_WRITE_ERROR_PROPERTY, str(exc))
            if hasattr(reply, "abort"):
                reply.abort()

    def _handle_download_finished(self, reply: object) -> None:
        pending = self._downloads.pop(reply, None)
        if pending is None:
            self._cleanup_reply(reply)
            return

        self._handle_download_ready_read(reply)

        write_error = reply.property(_WRITE_ERROR_PROPERTY)
        if write_error:
            pending.partial_path.unlink(missing_ok=True)
            self._cleanup_reply(reply)
            self.download_finished.emit(
                UpdateDownloadResult(
                    success=False,
                    version=pending.version,
                    installer_url=pending.installer_url,
                    error=f"Không ghi được installer tải về: {write_error}",
                )
            )
            return

        if self._has_network_error(reply):
            pending.partial_path.unlink(missing_ok=True)
            error = self._reply_error_message(reply, "tải installer cập nhật")
            self._cleanup_reply(reply)
            self.download_finished.emit(
                UpdateDownloadResult(
                    success=False,
                    version=pending.version,
                    installer_url=pending.installer_url,
                    error=error,
                )
            )
            return

        try:
            if not pending.partial_path.exists() or pending.partial_path.stat().st_size <= 0:
                raise OSError("File installer tải về rỗng.")
            pending.partial_path.replace(pending.final_path)
        except OSError as exc:
            LOGGER.exception("Không thể hoàn tất file installer cập nhật %s", pending.final_path)
            pending.partial_path.unlink(missing_ok=True)
            self._cleanup_reply(reply)
            self.download_finished.emit(
                UpdateDownloadResult(
                    success=False,
                    version=pending.version,
                    installer_url=pending.installer_url,
                    error=f"Không lưu được installer cập nhật: {exc}",
                )
            )
            return

        self._cleanup_reply(reply)
        self.download_finished.emit(
            UpdateDownloadResult(
                success=True,
                version=pending.version,
                installer_url=pending.installer_url,
                installer_path=pending.final_path,
            )
        )

    def _attach_timeout(self, reply: object) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._abort_reply_for_timeout(reply))
        timer.start(self._timeout_ms)
        self._timers[reply] = timer

    def _abort_reply_for_timeout(self, reply: object) -> None:
        reply.setProperty(_TIMEOUT_PROPERTY, True)
        if hasattr(reply, "abort"):
            reply.abort()

    def _cleanup_reply(self, reply: object) -> None:
        timer = self._timers.pop(reply, None)
        if timer is not None:
            timer.stop()
            timer.deleteLater()
        if hasattr(reply, "deleteLater"):
            reply.deleteLater()

    def _has_network_error(self, reply: object) -> bool:
        return reply.error() != QNetworkReply.NetworkError.NoError

    def _reply_error_message(self, reply: object, action: str) -> str:
        if bool(reply.property(_TIMEOUT_PROPERTY)):
            return f"Yêu cầu {action} đã hết thời gian chờ."
        error_message = reply.errorString().strip()
        if error_message:
            return f"Không thể {action}: {error_message}"
        return f"Không thể {action}."

    def _build_launcher_script(self, installer_path: Path, *, wait_for_pid: int) -> str:
        escaped_installer_path = _escape_batch_value(str(installer_path))
        escaped_args = " ".join(_INSTALLER_ARGS)
        if escaped_args:
            escaped_args = f" {escaped_args}"
        return "\n".join(
            [
                "@echo off",
                "setlocal",
                f'set "TARGET_PID={wait_for_pid}"',
                f'set "INSTALLER_PATH={escaped_installer_path}"',
                "timeout /t 2 /nobreak >nul",
                ":wait_for_app_exit",
                'tasklist /FI "PID eq %TARGET_PID%" 2>nul | find "%TARGET_PID%" >nul',
                "if not errorlevel 1 (",
                "    timeout /t 1 /nobreak >nul",
                "    goto wait_for_app_exit",
                ")",
                f'start "" "%INSTALLER_PATH%"{escaped_args}',
                'del "%~f0" >nul 2>&1',
                "exit /b 0",
                "",
            ]
        )


def _normalize_version(value: str) -> tuple[int, ...]:
    normalized = value.strip().lstrip("vV")
    if not normalized:
        raise ValueError("Version không được để trống.")
    parts = normalized.split(".")
    if any(not part.isdigit() for part in parts):
        raise ValueError(f"Version không hợp lệ: {value}")
    return tuple(int(part) for part in parts)


def _require_string_field(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Manifest cập nhật thiếu trường {key}.")
    return value.strip()


def _is_supported_url(value: str) -> bool:
    parsed = urlparse(value.strip())
    return parsed.scheme.lower() in _ALLOWED_URL_SCHEMES and bool(parsed.netloc)


def _read_reply_bytes(reply: object) -> bytes:
    data = reply.readAll()
    return bytes(data)


def _escape_batch_value(value: str) -> str:
    return value.replace("%", "%%")
