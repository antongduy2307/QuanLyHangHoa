from __future__ import annotations

from datetime import date
import unittest
from unittest.mock import patch

from PyQt6.QtWidgets import QApplication, QMessageBox

from core.exceptions import ValidationError
from modules.attendance.inventory_diagnostic_service import (
    AttendanceInventoryDiagnosticIssue,
    AttendanceInventoryIssueType,
)
from modules.settings.service import SettingsService
from modules.settings.ui.page import AttendanceInventoryDiagnosticsPanel, SettingsPage


class _FakeDiagnosticService:
    def __init__(self, issues: list[AttendanceInventoryDiagnosticIssue] | None = None) -> None:
        self.issues = list(issues or [])
        self.list_calls = 0
        self.reconcile_calls: list[int] = []
        self.reconcile_error: Exception | None = None

    def list_issues(self) -> list[AttendanceInventoryDiagnosticIssue]:
        self.list_calls += 1
        return list(self.issues)

    def reconcile_daily_record(self, daily_record_id: int) -> object:
        self.reconcile_calls.append(daily_record_id)
        if self.reconcile_error is not None:
            raise self.reconcile_error
        self.issues = []
        return object()


def _issue(
    issue_type: AttendanceInventoryIssueType = AttendanceInventoryIssueType.MISSING_EFFECTS_FOR_DONE_RECORD,
    *,
    daily_record_id: int = 10,
) -> AttendanceInventoryDiagnosticIssue:
    return AttendanceInventoryDiagnosticIssue(
        issue_type=issue_type,
        severity="warning",
        daily_record_id=daily_record_id,
        employee_id=7,
        work_date=date(2026, 5, 13),
        message="diagnostic message",
        expected_lines_summary="product=1:unit=BAO:qty=5",
        actual_effects_summary="",
    )


class AttendanceInventoryDiagnosticsUITestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._app = QApplication.instance() or QApplication([])

    def test_diagnostics_panel_loads_with_no_issues(self) -> None:
        panel = AttendanceInventoryDiagnosticsPanel(_FakeDiagnosticService())

        panel.scan_issues()

        self.assertEqual(panel.issues_table.rowCount(), 0)
        self.assertIn("Không phát hiện", panel.status_label.text())

    def test_scan_calls_list_issues_and_shows_no_issue_message(self) -> None:
        service = _FakeDiagnosticService()
        panel = AttendanceInventoryDiagnosticsPanel(service)

        panel.scan_button.click()

        self.assertEqual(service.list_calls, 1)
        self.assertIn("Không phát hiện lệch tồn kho từ chấm công", panel.status_label.text())

    def test_issues_render_with_vietnamese_labels(self) -> None:
        panel = AttendanceInventoryDiagnosticsPanel(
            _FakeDiagnosticService([_issue(AttendanceInventoryIssueType.QUANTITY_MISMATCH)])
        )

        panel.scan_issues()

        self.assertEqual(panel.issues_table.rowCount(), 1)
        self.assertEqual(panel.issues_table.item(0, 2).text(), "Lệch số lượng")
        self.assertEqual(panel.issues_table.item(0, 4).text(), "diagnostic message")

    def test_selecting_issue_enables_reconcile_button_when_source_exists(self) -> None:
        panel = AttendanceInventoryDiagnosticsPanel(_FakeDiagnosticService([_issue()]))
        panel.scan_issues()

        panel.issues_table.selectRow(0)

        self.assertTrue(panel.reconcile_button.isEnabled())

    def test_reconcile_button_disabled_for_missing_source_issue(self) -> None:
        panel = AttendanceInventoryDiagnosticsPanel(
            _FakeDiagnosticService([_issue(AttendanceInventoryIssueType.STALE_EFFECTS_FOR_MISSING_DAILY_RECORD)])
        )
        panel.scan_issues()

        panel.issues_table.selectRow(0)

        self.assertFalse(panel.reconcile_button.isEnabled())

    def test_confirmed_reconcile_calls_service_and_refreshes(self) -> None:
        service = _FakeDiagnosticService([_issue(daily_record_id=42)])
        panel = AttendanceInventoryDiagnosticsPanel(service)
        panel.scan_issues()
        panel.issues_table.selectRow(0)

        with patch(
            "modules.settings.ui.page.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch("shared.widgets.message_box.MessageBox.info"):
            panel.reconcile_button.click()

        self.assertEqual(service.reconcile_calls, [42])
        self.assertGreaterEqual(service.list_calls, 2)
        self.assertEqual(panel.issues_table.rowCount(), 0)

    def test_reconcile_failure_shows_error_and_does_not_crash(self) -> None:
        service = _FakeDiagnosticService([_issue(daily_record_id=42)])
        service.reconcile_error = ValidationError("bad sync")
        panel = AttendanceInventoryDiagnosticsPanel(service)
        panel.scan_issues()
        panel.issues_table.selectRow(0)

        with patch(
            "modules.settings.ui.page.QMessageBox.question",
            return_value=QMessageBox.StandardButton.Yes,
        ), patch("shared.widgets.message_box.MessageBox.error") as error:
            panel.reconcile_button.click()

        self.assertEqual(service.reconcile_calls, [42])
        error.assert_called_once()

    def test_scan_is_read_only_and_does_not_reconcile(self) -> None:
        service = _FakeDiagnosticService([_issue()])
        panel = AttendanceInventoryDiagnosticsPanel(service)

        panel.scan_issues()

        self.assertEqual(service.list_calls, 1)
        self.assertEqual(service.reconcile_calls, [])

    def test_settings_page_contains_admin_diagnostics_panel(self) -> None:
        with patch("modules.attendance.ui.settings_tab.AttendancePriceSettingsTab.reload"):
            page = SettingsPage(SettingsService(), diagnostic_service=_FakeDiagnosticService())

        panel = page.findChild(AttendanceInventoryDiagnosticsPanel)

        self.assertIsNotNone(panel)


if __name__ == "__main__":
    unittest.main()
