from __future__ import annotations

import shutil
import time
import unittest
from pathlib import Path
from uuid import uuid4

from PyQt6.QtCore import QByteArray, QCoreApplication, QObject, QTimer, pyqtSignal
from PyQt6.QtNetwork import QNetworkReply

from core.config import Settings
from modules.update.service import UpdateCheckResult, UpdateDownloadResult, UpdateService, build_update_check_result, compare_versions, parse_update_manifest


class FakeReply(QObject):
    finished = pyqtSignal()
    readyRead = pyqtSignal()
    downloadProgress = pyqtSignal(int, int)

    def __init__(
        self,
        *,
        body: bytes = b"",
        error: QNetworkReply.NetworkError = QNetworkReply.NetworkError.NoError,
        error_string: str = "",
        auto_finish: bool = True,
    ) -> None:
        super().__init__()
        self._body = QByteArray(body)
        self._buffer_consumed = False
        self._error = error
        self._error_string = error_string
        self._aborted = False
        if auto_finish:
            QTimer.singleShot(0, self._emit_finished)

    def _emit_finished(self) -> None:
        if not self._buffer_consumed and not self._body.isEmpty():
            size = self._body.size()
            self.readyRead.emit()
            self.downloadProgress.emit(size, size)
        self.finished.emit()

    def abort(self) -> None:
        self._error = QNetworkReply.NetworkError.OperationCanceledError
        self._error_string = "aborted"
        if not self._aborted:
            self._aborted = True
            QTimer.singleShot(0, self.finished.emit)

    def deleteLater(self) -> None:
        super().deleteLater()

    def error(self) -> QNetworkReply.NetworkError:
        return self._error

    def errorString(self) -> str:
        return self._error_string

    def readAll(self) -> QByteArray:
        if self._buffer_consumed:
            return QByteArray()
        self._buffer_consumed = True
        return QByteArray(self._body)


class FakeNetworkAccessManager(QObject):
    def __init__(self, responses: dict[str, dict[str, object]]) -> None:
        super().__init__()
        self._responses = responses
        self.requests: list[str] = []

    def get(self, request: object) -> FakeReply:
        url = request.url().toString()
        self.requests.append(url)
        config = self._responses[url]
        return FakeReply(**config)


class UpdateServiceTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QCoreApplication.instance() or QCoreApplication([])
        cls._workspace_temp_root = Path(__file__).resolve().parent / "_tmp"
        cls._workspace_temp_root.mkdir(parents=True, exist_ok=True)

    def setUp(self) -> None:
        self.temp_root = self._workspace_temp_root / uuid4().hex
        self.temp_root.mkdir(parents=True, exist_ok=False)
        self.settings = Settings(
            app_name="Quản lý Hàng hóa",
            app_data_dir=self.temp_root / "appdata",
            db_path=self.temp_root / "appdata" / "app.db",
            export_dir=self.temp_root / "appdata" / "exports",
            backup_dir=self.temp_root / "appdata" / "backups",
            temp_dir=self.temp_root / "appdata" / "temp",
            log_level="INFO",
            update_manifest_url="https://example.com/manifest.json",
            update_check_timeout_ms=25,
            update_startup_delay_ms=10,
        )

    def tearDown(self) -> None:
        shutil.rmtree(self.temp_root, ignore_errors=True)

    def test_compare_versions_uses_numeric_semver_order(self) -> None:
        self.assertLess(compare_versions("0.2.9", "0.3.0"), 0)
        self.assertEqual(compare_versions("0.3.0", "0.3.0"), 0)
        self.assertGreater(compare_versions("0.10.0", "0.9.9"), 0)
        self.assertEqual(compare_versions("v0.3.0", "0.3.0"), 0)

    def test_build_update_check_result_marks_forced_update(self) -> None:
        manifest = parse_update_manifest(
            b'{"version":"0.3.0","installer_url":"https://example.com/QuanLyHangHoa-Setup-0.3.0.exe","notes":["Fix"],"min_required_version":"0.2.5"}'
        )
        result = build_update_check_result(manifest, current_version="0.2.0", manifest_url=self.settings.update_manifest_url)
        self.assertTrue(result.has_update)
        self.assertTrue(result.is_forced_update)
        self.assertEqual(result.latest_version, "0.3.0")

    def test_build_update_check_result_treats_forced_update_as_update(self) -> None:
        manifest = parse_update_manifest(
            b'{"version":"0.2.0","installer_url":"https://example.com/QuanLyHangHoa-Setup-0.2.0.exe","notes":["Fix"],"min_required_version":"0.2.5"}'
        )
        result = build_update_check_result(manifest, current_version="0.2.0", manifest_url=self.settings.update_manifest_url)
        self.assertTrue(result.has_update)
        self.assertTrue(result.is_forced_update)

    def test_check_for_update_reports_new_version(self) -> None:
        network = FakeNetworkAccessManager(
            {
                self.settings.update_manifest_url: {
                    "body": b'{"version":"0.3.0","installer_url":"https://example.com/downloads/QuanLyHangHoa-Setup-0.3.0.exe","notes":["Sua loi"],"min_required_version":"0.2.5"}'
                }
            }
        )
        service = UpdateService(settings=self.settings, current_version="0.2.0", network_manager=network)
        results: list[UpdateCheckResult] = []
        service.check_finished.connect(results.append)

        service.check_for_update()
        self._pump_events()

        self.assertEqual(network.requests, [self.settings.update_manifest_url])
        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].has_update)
        self.assertTrue(results[0].is_forced_update)

    def test_check_for_update_handles_invalid_json(self) -> None:
        network = FakeNetworkAccessManager({self.settings.update_manifest_url: {"body": b"{invalid json"}})
        service = UpdateService(settings=self.settings, current_version="0.2.0", network_manager=network)
        results: list[UpdateCheckResult] = []
        service.check_finished.connect(results.append)

        service.check_for_update()
        self._pump_events()

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].has_update)
        self.assertIsNotNone(results[0].error)

    def test_check_for_update_handles_network_error(self) -> None:
        network = FakeNetworkAccessManager(
            {
                self.settings.update_manifest_url: {
                    "body": b"",
                    "error": QNetworkReply.NetworkError.HostNotFoundError,
                    "error_string": "host not found",
                }
            }
        )
        service = UpdateService(settings=self.settings, current_version="0.2.0", network_manager=network)
        results: list[UpdateCheckResult] = []
        service.check_finished.connect(results.append)

        service.check_for_update()
        self._pump_events()

        self.assertEqual(len(results), 1)
        self.assertIn("host not found", results[0].error or "")

    def test_download_installer_saves_file_to_temp_dir(self) -> None:
        installer_url = "https://example.com/downloads/QuanLyHangHoa-Setup-0.3.0.exe"
        network = FakeNetworkAccessManager({installer_url: {"body": b"fake installer bytes"}})
        service = UpdateService(settings=self.settings, current_version="0.2.0", network_manager=network)
        results: list[UpdateDownloadResult] = []
        service.download_finished.connect(results.append)

        service.download_installer(installer_url, "0.3.0")
        self._pump_events()

        self.assertEqual(len(results), 1)
        self.assertTrue(results[0].success)
        self.assertIsNotNone(results[0].installer_path)
        installer_path = results[0].installer_path
        self.assertIsNotNone(installer_path)
        self.assertTrue(installer_path.exists())
        self.assertEqual(installer_path.read_bytes(), b"fake installer bytes")

    def test_download_installer_rejects_invalid_url(self) -> None:
        service = UpdateService(settings=self.settings, current_version="0.2.0")
        results: list[UpdateDownloadResult] = []
        service.download_finished.connect(results.append)

        service.download_installer("notaurl", "0.3.0")

        self.assertEqual(len(results), 1)
        self.assertFalse(results[0].success)
        self.assertIn("không hợp lệ", (results[0].error or "").lower())

    def test_check_for_update_times_out(self) -> None:
        network = FakeNetworkAccessManager({self.settings.update_manifest_url: {"body": b"", "auto_finish": False}})
        service = UpdateService(settings=self.settings, current_version="0.2.0", network_manager=network, timeout_ms=10)
        results: list[UpdateCheckResult] = []
        service.check_finished.connect(results.append)

        service.check_for_update()
        self._pump_events(timeout_seconds=0.2)

        self.assertEqual(len(results), 1)
        self.assertIn("hết thời gian chờ", results[0].error or "")

    def test_create_launcher_script_waits_for_app_exit(self) -> None:
        service = UpdateService(settings=self.settings, current_version="0.2.0")
        installer_path = self.settings.temp_dir / "QuanLyHangHoa-Setup-0.3.0.exe"
        launcher_path = service.create_launcher_script(installer_path, wait_for_pid=4321)

        content = launcher_path.read_text(encoding="utf-8")
        self.assertIn('set "TARGET_PID=4321"', content)
        self.assertIn('start "" "%INSTALLER_PATH%" /NORESTART', content)
        self.assertIn("tasklist /FI", content)

    def _pump_events(self, *, timeout_seconds: float = 0.1) -> None:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            self._app.processEvents()
            time.sleep(0.005)


if __name__ == "__main__":
    unittest.main()
