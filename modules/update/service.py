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
from core.utils import ensure_directories
from core.version import APP_VERSION


LOGGER = get_logger(__name__)
_ALLOWED_URL_SCHEMES = {"http", "https"}
_TIMEOUT_PROPERTY = "updateTimedOut"
_WRITE_ERROR_PROPERTY = "updateWriteError"
_INSTALLER_ARGS: tuple[str, ...] = ("/NORESTART",)
_RETRYABLE_NETWORK_ERRORS = {
    QNetworkReply.NetworkError.TimeoutError,
    QNetworkReply.NetworkError.TemporaryNetworkFailureError,
    QNetworkReply.NetworkError.NetworkSessionFailedError,
    QNetworkReply.NetworkError.UnknownNetworkError,
    QNetworkReply.NetworkError.ProxyTimeoutError,
    QNetworkReply.NetworkError.ServiceUnavailableError,
}


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
    installer_name: str
    version: str
    installer_url: str
    attempt: int
    max_attempts: int


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
        download_timeout_ms: int | None = None,
        download_retry_count: int | None = None,
        network_manager: QNetworkAccessManager | None = None,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings or get_settings()
        self._current_version = current_version
        self._manifest_url = manifest_url or self._settings.update_manifest_url
        self._check_timeout_ms = timeout_ms or self._settings.update_check_timeout_ms
        self._download_timeout_ms = download_timeout_ms or self._settings.update_download_timeout_ms
        self._download_retry_count = max(1, download_retry_count or self._settings.update_download_retry_count)
        self._network = network_manager or QNetworkAccessManager(self)
        self._timers: dict[object, QTimer] = {}
        self._downloads: dict[object, _PendingDownload] = {}

    def check_for_update(self, manifest_url: str | None = None) -> None:
        target_url = (manifest_url or self._manifest_url).strip()
        LOGGER.info("Update manifest check started | url=%s | timeout_ms=%s", target_url, self._check_timeout_ms)
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
        self._attach_timeout(reply, self._check_timeout_ms)
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
        LOGGER.info(
            "Installer download requested | version=%s | url=%s | installer_name=%s | final_path=%s | timeout_ms=%s | retries=%s",
            version,
            target_url,
            installer_name,
            final_path,
            self._download_timeout_ms,
            self._download_retry_count,
        )
        self._start_download_attempt(
            _PendingDownload(
                partial_path=partial_path,
                final_path=final_path,
                installer_name=installer_name,
                version=version,
                installer_url=target_url,
                attempt=1,
                max_attempts=self._download_retry_count,
            )
        )

    def build_installer_filename(self, installer_url: str, version: str) -> str:
        file_name = PurePosixPath(urlparse(installer_url).path).name
        if file_name and file_name.lower().endswith(".exe"):
            return file_name
        return f"{self._settings.runtime_dir_name}-Setup-{version}.exe"

    def create_launcher_script(self, installer_path: Path, *, wait_for_pid: int | None = None) -> Path:
        validated_installer_path = self._validate_installer_file(installer_path)
        ensure_directories([self._settings.temp_dir])
        launcher_path = self._settings.temp_dir / f"launch-update-{validated_installer_path.stem}.cmd"
        launcher_path.write_text(
            self._build_launcher_script(validated_installer_path, wait_for_pid=wait_for_pid or os.getpid()),
            encoding="utf-8",
        )
        LOGGER.info("Update launcher script created | launcher_path=%s | installer_path=%s", launcher_path, validated_installer_path)
        return launcher_path

    def launch_installer_after_exit(self, installer_path: Path, *, wait_for_pid: int | None = None) -> Path:
        validated_installer_path = self._validate_installer_file(installer_path)
        launcher_path = self.create_launcher_script(validated_installer_path, wait_for_pid=wait_for_pid)
        command = os.environ.get("COMSPEC", "cmd.exe")
        LOGGER.info("Launching updater handoff | launcher_path=%s | installer_path=%s", launcher_path, validated_installer_path)
        started = QProcess.startDetached(command, ["/c", str(launcher_path)])
        if not started:
            raise RuntimeError("Không thể khởi chạy launcher cập nhật.")
        return launcher_path

    def _start_download_attempt(self, pending: _PendingDownload) -> None:
        pending.final_path.unlink(missing_ok=True)
        pending.partial_path.unlink(missing_ok=True)

        request = QNetworkRequest(QUrl(pending.installer_url))
        reply = self._network.get(request)
        self._downloads[reply] = pending
        self._attach_timeout(reply, self._download_timeout_ms)
        reply.readyRead.connect(lambda: self._handle_download_ready_read(reply))
        reply.downloadProgress.connect(lambda received, total: self._handle_download_progress(reply, received, total))
        reply.finished.connect(lambda: self._handle_download_finished(reply))
        LOGGER.info(
            "Installer download started | attempt=%s/%s | url=%s | partial_path=%s | final_path=%s",
            pending.attempt,
            pending.max_attempts,
            pending.installer_url,
            pending.partial_path,
            pending.final_path,
        )

    def _handle_check_finished(self, reply: object, manifest_url: str) -> None:
        LOGGER.info("Update manifest check finished | url=%s | http_status=%s", manifest_url, self._http_status_code(reply))
        if self._has_network_error(reply):
            error = self._reply_error_message(reply, "kiểm tra cập nhật")
            LOGGER.warning(
                "Update manifest check failed | url=%s | error_type=%s | timed_out=%s | http_status=%s | error=%s",
                manifest_url,
                reply.error(),
                bool(reply.property(_TIMEOUT_PROPERTY)),
                self._http_status_code(reply),
                error,
            )
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
            LOGGER.info(
                "Update manifest parsed | latest_version=%s | min_required_version=%s | installer_url=%s",
                manifest.version,
                manifest.min_required_version,
                manifest.installer_url,
            )
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

        self._reset_timeout(reply)
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

    def _handle_download_progress(self, reply: object, received: int, total: int) -> None:
        if reply in self._downloads:
            self._reset_timeout(reply)
        self.download_progress.emit(received, total)

    def _handle_download_finished(self, reply: object) -> None:
        pending = self._downloads.pop(reply, None)
        if pending is None:
            self._cleanup_reply(reply)
            return

        self._handle_download_ready_read(reply)
        LOGGER.info(
            "Installer download finished | attempt=%s/%s | url=%s | http_status=%s",
            pending.attempt,
            pending.max_attempts,
            pending.installer_url,
            self._http_status_code(reply),
        )

        write_error = reply.property(_WRITE_ERROR_PROPERTY)
        if write_error:
            pending.partial_path.unlink(missing_ok=True)
            self._cleanup_reply(reply)
            self._emit_download_failure(
                pending,
                f"Không ghi được installer tải về: {write_error}",
                retryable=False,
            )
            return

        if self._has_download_failure(reply):
            error = self._reply_error_message(reply, "tải installer cập nhật")
            retryable = self._is_retryable_download_error(reply)
            pending.partial_path.unlink(missing_ok=True)
            self._cleanup_reply(reply)
            self._emit_download_failure(pending, error, retryable=retryable)
            return

        try:
            final_path = self._finalize_download_file(pending)
        except (OSError, RuntimeError) as exc:
            LOGGER.exception("Không thể hoàn tất file installer cập nhật %s", pending.final_path)
            pending.partial_path.unlink(missing_ok=True)
            pending.final_path.unlink(missing_ok=True)
            self._cleanup_reply(reply)
            self._emit_download_failure(
                pending,
                f"Không lưu được installer cập nhật: {exc}",
                retryable=False,
            )
            return

        self._cleanup_reply(reply)
        LOGGER.info(
            "Installer download success | version=%s | installer_url=%s | installer_path=%s | installer_name=%s",
            pending.version,
            pending.installer_url,
            final_path,
            pending.installer_name,
        )
        self.download_finished.emit(
            UpdateDownloadResult(
                success=True,
                version=pending.version,
                installer_url=pending.installer_url,
                installer_path=final_path,
            )
        )

    def _finalize_download_file(self, pending: _PendingDownload) -> Path:
        if not pending.partial_path.exists():
            raise OSError("File installer tải về không tồn tại.")
        if pending.partial_path.stat().st_size <= 0:
            raise OSError("File installer tải về rỗng.")
        pending.partial_path.replace(pending.final_path)
        return self._validate_installer_file(pending.final_path)

    def _validate_installer_file(self, installer_path: Path) -> Path:
        resolved_path = installer_path.resolve()
        if not resolved_path.exists():
            raise RuntimeError("Không tìm thấy file installer đã tải.")
        if resolved_path.suffix.lower() != ".exe":
            raise RuntimeError("File cập nhật tải về không phải .exe hợp lệ.")
        if resolved_path.stat().st_size <= 0:
            raise RuntimeError("File installer tải về bị rỗng.")
        return resolved_path

    def _emit_download_failure(self, pending: _PendingDownload, error: str, *, retryable: bool) -> None:
        LOGGER.warning(
            "Installer download failed | attempt=%s/%s | retryable=%s | url=%s | final_path=%s | error=%s",
            pending.attempt,
            pending.max_attempts,
            retryable,
            pending.installer_url,
            pending.final_path,
            error,
        )
        if retryable and pending.attempt < pending.max_attempts:
            retry_pending = _PendingDownload(
                partial_path=pending.partial_path,
                final_path=pending.final_path,
                installer_name=pending.installer_name,
                version=pending.version,
                installer_url=pending.installer_url,
                attempt=pending.attempt + 1,
                max_attempts=pending.max_attempts,
            )
            LOGGER.info(
                "Retrying installer download | next_attempt=%s/%s | url=%s",
                retry_pending.attempt,
                retry_pending.max_attempts,
                retry_pending.installer_url,
            )
            self._start_download_attempt(retry_pending)
            return

        self.download_finished.emit(
            UpdateDownloadResult(
                success=False,
                version=pending.version,
                installer_url=pending.installer_url,
                error=error,
            )
        )

    def _attach_timeout(self, reply: object, timeout_ms: int) -> None:
        timer = QTimer(self)
        timer.setSingleShot(True)
        timer.timeout.connect(lambda: self._abort_reply_for_timeout(reply))
        timer.setProperty("timeoutMs", timeout_ms)
        timer.start(timeout_ms)
        self._timers[reply] = timer

    def _reset_timeout(self, reply: object) -> None:
        timer = self._timers.get(reply)
        if timer is None:
            return
        timeout_ms = timer.property("timeoutMs")
        try:
            normalized_timeout = int(timeout_ms)
        except (TypeError, ValueError):
            return
        timer.start(normalized_timeout)

    def _abort_reply_for_timeout(self, reply: object) -> None:
        LOGGER.warning("Update network request timed out | timeout_ms=%s", self._timers.get(reply).property("timeoutMs") if reply in self._timers else None)
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

    def _has_download_failure(self, reply: object) -> bool:
        if self._has_network_error(reply):
            return True
        http_status = self._http_status_code(reply)
        return http_status is not None and http_status >= 400

    def _is_retryable_download_error(self, reply: object) -> bool:
        if bool(reply.property(_TIMEOUT_PROPERTY)):
            return True
        http_status = self._http_status_code(reply)
        if http_status in {408, 429} or (http_status is not None and http_status >= 500):
            return True
        return reply.error() in _RETRYABLE_NETWORK_ERRORS

    def _reply_error_message(self, reply: object, action: str) -> str:
        if bool(reply.property(_TIMEOUT_PROPERTY)):
            return f"Không thể {action}: yêu cầu đã hết thời gian chờ. Đây chỉ là lỗi mạng của tác vụ cập nhật; ứng dụng vẫn có thể dùng bình thường."
        http_status = self._http_status_code(reply)
        if http_status is not None and http_status >= 400:
            return f"Không thể {action}: HTTP {http_status}."
        error_message = reply.errorString().strip()
        if error_message:
            return f"Không thể {action}: {error_message}"
        return f"Không thể {action}."

    def _http_status_code(self, reply: object) -> int | None:
        if not hasattr(reply, "attribute"):
            return None
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        if status is None:
            return None
        try:
            return int(status)
        except (TypeError, ValueError):
            return None

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
