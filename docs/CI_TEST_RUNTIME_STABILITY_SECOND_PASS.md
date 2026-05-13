# CI Test Runtime Stability - Second Pass

## A. Files Inspected

- `.gitignore`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`
- `scripts/build_release.ps1`
- `shell/app_window.py`
- `shell/history_page.py`
- `modules/sales/ui/transaction_history_view.py`
- `core/config.py`
- `core/db.py`
- `modules/attendance/db.py`
- `core/logging.py`
- `tests/test_smoke.py`
- `tests/test_app_window_attendance_sync.py`
- `tests/test_settings_backup.py`
- `tests/test_update_service.py`
- `tests/test_ui_scale_settings.py`
- `tests/test_diagnostics_service.py`
- `tests/test_reporting_refresh.py`
- `tests/test_overpayment_ordering_pipeline.py`
- Direct `TransactionHistoryView` tests:
  - `tests/test_history_delete_actions.py`
  - `tests/test_history_search_suggestions.py`
  - `tests/test_history_datetime_actions.py`

## B. Temp-Dir Root Cause

Repo-local temp roots were still used by several tests:

- `tests/test_update_service.py`
  - Created `tests/_tmp/<uuid>`.
  - Update download tests wrote temporary installer files under that tree.
- `tests/test_settings_backup.py`
  - Created `tests/_tmp/settings-backup`.
  - Backup and settings-page tests wrote app DB / attendance DB / export files under that tree.
- `tests/test_ui_scale_settings.py`
  - Created `tests/_ui_scale_tmp/<uuid>`.
  - QSettings wrote `.ini` files under the repo.

Existing stale folders also remained under:

- `tests/_tmp`
- `tests/_diagnostics_tmp`
- `tests/_ui_scale_tmp`

These repo-local runtime folders can be locked by SQLite, QSettings, logging handlers, or Qt objects and then produce Git warnings such as:

`warning: could not open directory 'tests/_tmp/...': Permission denied`

The tests now use system temporary directories via `tempfile.TemporaryDirectory()` or `tempfile.mkdtemp()` outside the repository. `.gitignore` still ignores `tests/_tmp/`, `tests/_diagnostics_tmp/`, and `tests/_ui_scale_tmp/` as a safety net.

## C. DB / Log / Qt Lock Cleanup Changes

Changed:

- `tests/test_update_service.py`
  - Moved update runtime root from `tests/_tmp` to `tempfile.TemporaryDirectory(prefix="update-service-")`.
- `tests/test_settings_backup.py`
  - Moved backup runtime root from `tests/_tmp/settings-backup` to `tempfile.TemporaryDirectory(prefix="settings-backup-")`.
  - Resets and disposes the main DB engine in teardown.
  - Initializes the main DB only for the SettingsPage UI test that constructs DB-backed settings UI.
- `tests/test_ui_scale_settings.py`
  - Moved QSettings root from `tests/_ui_scale_tmp` to `tempfile.TemporaryDirectory(prefix="ui-scale-settings-")`.
- `tests/helpers/runtime.py`
  - Added `TempMainDbRuntime`, a shared context manager for real DB-backed UI smoke tests.
  - Sets portable temp runtime env vars.
  - Clears settings cache.
  - Resets SQLAlchemy engine/session factory.
  - Calls `core.db.init_db()`.
  - Asserts `app.db` exists and `invoices` table exists.
  - Closes root logging handlers and resets DB/settings on cleanup.
- `tests/test_smoke.py`
  - Uses `TempMainDbRuntime` for every smoke test so discovery order cannot leave it using a stale engine from another test.
  - Closes all Qt windows and processes events in teardown.
- `tests/test_app_window_attendance_sync.py`
  - Closes all Qt windows and processes events in teardown.
  - Uses a fake HistoryPage so attendance-tab tests do not accidentally construct sales DB-backed history UI.

Stale repo-local temp folders were removed after test fixes.

## D. No-Such-Table Remaining Caller Analysis

The remaining unsafe caller was:

- `tests/test_app_window_attendance_sync.py`

Why:

- It constructs `AppWindow`.
- Its module list places `attendance` before `settings`.
- `AppWindow` inserts `HistoryPage` before Attendance/Settings.
- A real `HistoryPage` constructs `TransactionHistoryView`.
- `TransactionHistoryView.__init__()` calls `reload()`.
- `reload()` queries `invoices`.

That test does not validate history UI or sales DB behavior, so it should not construct the real sales DB-backed history page. It now patches `shell.app_window.HistoryPage` with a fake page that has the minimal `history_changed` signal stub and `reload_all_views()` method needed by `AppWindow`.

Other classifications:

- `tests/test_smoke.py`
  - Real AppWindow/HistoryPage path.
  - Safe now because `TempMainDbRuntime` initializes schema and asserts no history error dialog is called.
- `tests/test_reporting_refresh.py`
  - Safe because it already patches `shell.app_window.HistoryPage` with a fake page.
- `tests/test_history_delete_actions.py`
  - Safe because it uses controller stubs.
- `tests/test_history_search_suggestions.py`
  - Safe because it uses controller stubs.
- `tests/test_history_datetime_actions.py`
  - Safe because it uses controller stubs.
- `tests/test_overpayment_ordering_pipeline.py`
  - Safe because it uses an in-memory SQLite engine and creates schema with `Base.metadata.create_all()`.
- Production startup:
  - Safe because `shell.bootstrap.bootstrap_application()` calls `init_db()` before constructing `AppWindow`.

## E. Tests Updated

- `tests/helpers/__init__.py`
- `tests/helpers/runtime.py`
- `tests/test_smoke.py`
- `tests/test_app_window_attendance_sync.py`
- `tests/test_settings_backup.py`
- `tests/test_update_service.py`
- `tests/test_ui_scale_settings.py`
- `.gitignore`

The changes are test/CI lifecycle only. No sales business logic, schema design, attendance/product-sync behavior, or production message-box behavior was changed.

## F. Workflow Check

Confirmed:

- `.github/workflows/ci.yml`
  - `QT_QPA_PLATFORM: offscreen`
  - runtime dir configured under `$env:RUNNER_TEMP`
  - test command runs from `${{ github.workspace }}`
  - command: `python -m unittest discover -s tests -p "test*.py" -t .`
- `.github/workflows/release.yml`
  - `QT_QPA_PLATFORM: offscreen`
  - runtime dir configured under `$env:RUNNER_TEMP`
  - test command runs from `${{ github.workspace }}`
  - command: `python -m unittest discover -s tests -p "test*.py" -t .`
- `scripts/build_release.ps1`
  - command: `python -m unittest discover -s tests -p "test*.py" -t .`
  - command: `python -m compileall core modules tests shell`

## G. Verification Results

Changed-test command:

`python -m unittest tests.test_smoke tests.test_app_window_attendance_sync tests.test_update_service tests.test_settings_backup tests.test_ui_scale_settings`

Result:

- Passed, 34 tests.

Focused smoke command:

`python -m unittest tests.test_smoke`

Result:

- Passed, 3 tests.

Full CI-equivalent discovery:

`python -m unittest discover -s tests -p "test*.py" -t .`

Result:

- Passed, 407 tests in 24.465 seconds.

Compileall:

`python -m compileall core modules tests shell`

Result:

- Exit code 0.

Temp-dir checks:

- `tests/_tmp` was not recreated.
- `tests/_diagnostics_tmp` was not recreated.
- `git status --short` completed without permission warnings after stale temp folder cleanup.

Expected noisy logs:

- Diagnostics tests intentionally log mocked exceptions.
- Update-service tests intentionally log mocked network and missing-installer failures.
- Attendance sync tests intentionally log a mocked sync failure.

## H. Caveats

- The repository currently has tracked generated artifacts under `tests/__pycache__` and `tests/_ui_scale_tmp`. They were restored after verification so this task does not mix in unrelated repository cleanup. A separate source hygiene pass should remove tracked generated files from version control.
- `.gitignore` now ignores repo-local temp test roots as a safety net, but the fixed tests no longer rely on those ignored paths.
- `TransactionHistoryView.reload()` still catches errors and shows `MessageBox.error` in production. Tests that construct real DB-backed UI now either initialize schema first or mock unrelated DB-backed pages.
