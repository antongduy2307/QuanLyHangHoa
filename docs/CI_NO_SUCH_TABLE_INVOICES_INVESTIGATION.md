# CI Investigation: `no such table: invoices`

## A. Files Inspected

- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `scripts/build_release.ps1`
- `scripts/build_exe.ps1`
- `shell/bootstrap.py`
- `shell/app_window.py`
- `shell/history_page.py`
- `modules/sales/ui/transaction_history_view.py`
- `modules/sales/controller.py`
- `core/config.py`
- `core/paths.py`
- `core/db.py`
- `tests/test_smoke.py`
- `tests/test_app_window_attendance_sync.py`
- `tests/test_reporting_refresh.py`
- `tests/test_history_delete_actions.py`
- `tests/test_history_search_suggestions.py`
- `tests/test_history_datetime_actions.py`
- `tests/test_overpayment_ordering_pipeline.py`

## B. Exact Failing Command / Test / Workflow Step

The CI/CD command that can trigger this path is the unittest step.

Current CI workflow:

`python -m unittest discover -s tests -p "test*.py" -t .`

Current release workflow:

`python -m unittest discover -s tests -p "test*.py" -t .`

The legacy local release script was still using:

`python -m unittest discover tests`

That has been updated to:

`python -m unittest discover -s tests -p "test*.py" -t .`

The exact UI caller is:

- `tests/test_smoke.py::SmokeTestCase.test_main_tab_order_places_history_before_attendance_and_settings`

The call chain is:

1. `tests/test_smoke.py` constructs `AppWindow`.
2. `shell.app_window.AppWindow.__init__()` inserts a real `HistoryPage` before Attendance and Settings.
3. `shell.history_page.HistoryPage.__init__()` constructs `TransactionHistoryView`.
4. `modules.sales.ui.transaction_history_view.TransactionHistoryView.__init__()` calls `self.reload()`.
5. `TransactionHistoryView.reload()` calls `SalesController.list_transaction_history()`.
6. `SalesController.list_transaction_history()` calls `SalesRepository.list_invoices()`.
7. SQLAlchemy issues a `SELECT` from `invoices`.

The failure happens during unittest discovery, specifically while running the smoke test. It is not caused by PyInstaller analysis/build, app import alone, or a post-build smoke step.

## C. Root Cause

`TransactionHistoryView` intentionally auto-loads transaction history during construction. The smoke test created a real `AppWindow`, which creates a real `HistoryPage`, which creates a real `TransactionHistoryView`.

Before the fix, the smoke test used a manually constructed `Settings` object for `AppWindow`, but it did not guarantee that `core.db.SessionFactory` was bound to that same temporary DB path and did not initialize the schema for that DB before the UI auto-reload.

Because `core.db.ENGINE` and `SessionFactory` are module-level globals created from cached runtime settings, a test can accidentally point the sales controller at:

- a default runtime DB path rather than the smoke test's temp path, or
- an empty SQLite file created by opening a connection before `init_db()` ran.

In either case, `TransactionHistoryView.reload()` can query a database that exists but does not contain `invoices`, producing:

`sqlite3.OperationalError: no such table: invoices`

The production code path in `shell/bootstrap.py` is correct: it calls `init_db()` before constructing `AppWindow`. The broken setup was the UI smoke test.

## D. DB Path And Engine / Cache Findings

Main DB initialization is controlled by:

- `core.config.get_settings()`
- `core.paths.get_default_db_path()`
- `core.db.ENGINE`
- `core.db.SessionFactory`
- `core.db.reset_engine_cache()`
- `core.db.init_db()`

Findings:

1. `core.db.ENGINE` is created at module import time from `core.config.get_settings()`.
2. `core.config.get_settings()` is cached with `lru_cache`.
3. Changing environment variables or manually creating a `Settings` object does not automatically rebind `core.db.SessionFactory`.
4. `core.db.reset_engine_cache()` is the existing test helper that disposes the old engine and rebinds `SessionFactory` to the current cached settings.
5. Tests that change runtime paths must clear `core.config.get_settings` and then call `core.db.reset_engine_cache()`.
6. `core.db.init_db()` creates the DB parent directory, creates all main app tables, and runs migrations.
7. SQLite can create an empty DB file on first connection, so a DB file existing is not enough; the test must confirm the schema exists.

For the fixed smoke test:

- DB path is a portable temp path under the test's `tempfile.mkdtemp()` directory.
- Parent directory is created by `core.db.init_db()`.
- The DB file exists before `AppWindow` construction.
- The `invoices` table exists before `TransactionHistoryView.reload()` runs.
- The engine/session factory is reset before and after the test.

## E. UI Auto-Reload Findings

`TransactionHistoryView` behavior:

- `__init__()` calls `self.reload()`.
- `showEvent()` also calls `self.reload()`.
- `reload()` catches exceptions and calls `MessageBox.error(...)`.

`HistoryPage` behavior:

- Constructs `TransactionHistoryView`, `InvoiceListView`, `ReturnListView`, and `DebtPaymentListView`.
- Does not itself call `reload_all_views()` during construction, but child views may load themselves.

`AppWindow` behavior:

- Inserts `HistoryPage` before the large Attendance and Settings tabs.
- Does not call `reload_all_views()` during startup.
- Can call `reload_all_views()` later when transaction-changing pages emit signals.

Conclusion:

- UI construction currently expects the main DB schema to exist if real controllers/pages are used.
- This is acceptable production behavior because `shell.bootstrap.bootstrap_application()` calls `init_db()` before constructing `AppWindow`.
- Tests that instantiate real `AppWindow` or real history views must initialize DB schema first.
- Removing transaction history reload from production would be a broader behavioral change and was not needed.

## F. Chosen Fix Strategy

Chosen strategy: Option 1, test/workflow setup fix, plus a regression assertion.

Why:

- Production startup already initializes the DB before constructing pages.
- The failure was a smoke-test setup bug, not a sales logic bug.
- Removing or weakening `TransactionHistoryView.reload()` would change production behavior.
- Broadly swallowing SQLAlchemy errors would hide real setup/schema mistakes.

Implemented:

1. `tests/test_smoke.py` now patches portable temp runtime paths for the AppWindow smoke test.
2. It clears `core.config.get_settings` before binding the DB.
3. It calls `core.db.reset_engine_cache()`.
4. It calls `core.db.init_db()` before constructing `AppWindow`.
5. It asserts the DB file exists.
6. It asserts the `invoices` table exists.
7. It patches `modules.sales.ui.transaction_history_view.MessageBox.error` during construction and asserts it was not called.
8. It closes/deletes the window and resets DB/settings state in cleanup.
9. `scripts/build_release.ps1` now uses the same reliable unittest discovery command as CI/release workflows.

## G. Files Changed

- `tests/test_smoke.py`
  - Added temp runtime DB initialization before real `AppWindow` construction.
  - Added schema assertion for `invoices`.
  - Added regression assertion that transaction history reload does not call `MessageBox.error`.
  - Added Qt window cleanup.
- `scripts/build_release.ps1`
  - Updated unittest discovery command to `python -m unittest discover -s tests -p "test*.py" -t .`.
  - Updated compileall command to `python -m compileall core modules tests shell`.
- `docs/CI_NO_SUCH_TABLE_INVOICES_INVESTIGATION.md`
  - This investigation and fix report.

## H. Regression Test Added

The regression coverage is in:

- `tests/test_smoke.py::SmokeTestCase.test_main_tab_order_places_history_before_attendance_and_settings`

The test now proves:

- a temp DB path is used;
- the DB file exists after `init_db()`;
- `invoices` exists before `AppWindow` construction;
- constructing `AppWindow` triggers the real history page path without calling `TransactionHistoryView`'s error message box;
- the window closes cleanly.

This would have caught the original failure even if `TransactionHistoryView.reload()` caught the SQLAlchemy exception internally.

## I. Hang-Prevention Findings

The hang risk comes from this sequence:

1. `TransactionHistoryView.reload()` catches the `OperationalError`.
2. It calls `MessageBox.error(...)`.
3. In an offscreen CI environment, a modal message box can wait for user interaction and appear as a stuck workflow.

No production modal behavior was changed.

The smoke regression prevents the modal path by:

- initializing DB schema before UI construction;
- patching `TransactionHistoryView.MessageBox.error` during the smoke construction and asserting it is not called.

Other inspected tests that instantiate `TransactionHistoryView` directly use controller stubs or initialized service fixtures. `tests/test_reporting_refresh.py` patches `shell.app_window.HistoryPage` with a fake page, so it does not hit the real sales DB during AppWindow construction.

The workflows already set:

- `QT_QPA_PLATFORM=offscreen`
- `LOCALAPPDATA` under runner temp

No persistent Qt event loop is launched by the tests; they construct widgets under an existing `QApplication` and close windows in cleanup.

## J. Verification Commands / Results

Focused commands:

- `python -m unittest tests.test_smoke`
  - Result: passed, 3 tests.
- `python -m unittest tests.test_app_window_attendance_sync tests.test_reporting_refresh tests.test_history_delete_actions tests.test_history_search_suggestions tests.test_history_datetime_actions`
  - Result: passed, 19 tests.

Full CI-equivalent commands:

- `python -m unittest discover -s tests -p "test*.py" -t .`
  - Result: passed, 407 tests in 26.741 seconds.
- `python -m compileall core modules tests shell`
  - Result: exit code 0.

Workflow/script command string verification:

- `.github/workflows/ci.yml`
  - `QT_QPA_PLATFORM: offscreen`
  - `LOCALAPPDATA=$env:RUNNER_TEMP\QuanLyHangHoaTest`
  - `python -m unittest discover -s tests -p "test*.py" -t .`
  - `python -m compileall core modules tests shell`
- `.github/workflows/release.yml`
  - `QT_QPA_PLATFORM: offscreen`
  - `LOCALAPPDATA=$env:RUNNER_TEMP\QuanLyHangHoaTest`
  - `python -m unittest discover -s tests -p "test*.py" -t .`
  - `python -m compileall core modules tests shell`
- `scripts/build_release.ps1`
  - `python -m unittest discover -s tests -p "test*.py" -t .`
  - `python -m compileall core modules tests shell`

Notes:

- Full discovery prints expected diagnostic/update-service mocked failure logs, including the known `missing final exe` trace.
- `compileall` printed several `Can't list` messages for cleaned-up temporary test directories, but completed successfully with exit code 0.

## K. Caveats

- This fix does not change sales business logic.
- This fix does not change database schema design.
- This fix does not suppress production SQLAlchemy errors.
- This fix does not remove transaction history auto-reload.
- Future smoke tests that instantiate real DB-backed UI pages should use the same setup pattern: set temp paths, clear settings cache, reset engine, call `init_db()`, and assert no modal error path is invoked.
