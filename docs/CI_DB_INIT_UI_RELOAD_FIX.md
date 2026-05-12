# CI DB Init UI Reload Fix

## A. Files Inspected

- `tests/test_smoke.py`
- `shell/app_window.py`
- `shell/history_page.py`
- `modules/sales/ui/transaction_history_view.py`
- `core/db.py`
- `.github/workflows/ci.yml`
- `.github/workflows/release.yml`

## B. Root Cause

`AppWindow` always inserts a real `HistoryPage` before the large Attendance and Settings tabs. `HistoryPage` constructs `TransactionHistoryView`, and `TransactionHistoryView.__init__()` calls `reload()` immediately.

The smoke test `test_main_tab_order_places_history_before_attendance_and_settings` constructed `AppWindow` with a manually built `Settings` object, but it did not bind `core.db.SessionFactory` to that temp database path or call `core.db.init_db()` before the UI auto-reload happened.

That allowed the sales history query path to hit an empty SQLite database without schema:

`TransactionHistoryView.reload()` -> `SalesController.list_transaction_history()` -> `SalesRepository.list_invoices()` -> `SELECT FROM invoices`

The production view already catches and reports load errors, but the test setup was invalid for UI construction that touches the real main database.

## C. Failing Test / Caller

Caller:

- `tests/test_smoke.py::SmokeTestCase.test_main_tab_order_places_history_before_attendance_and_settings`

Indirect UI path:

- `shell.app_window.AppWindow.__init__`
- `shell.history_page.HistoryPage.__init__`
- `modules.sales.ui.transaction_history_view.TransactionHistoryView.__init__`
- `TransactionHistoryView.reload()`

## D. DB Init / Test Isolation Fix

`tests/test_smoke.py` now:

- uses a portable temporary app data directory.
- patches environment variables for the main app runtime paths.
- clears cached settings with `core.config.get_settings.cache_clear()`.
- rebuilds the SQLAlchemy engine/session factory with `core.db.reset_engine_cache()`.
- calls `core.db.init_db()` before constructing `AppWindow`.
- passes `core.config.get_settings()` into `AppWindow`, keeping the UI settings and `core.db.SessionFactory` aligned.

The test now initializes an empty but fully migrated main DB schema before any sales history auto-reload can run.

## E. UI Smoke Cleanup / Hang Prevention

`tests/test_smoke.py` now closes Qt windows and processes events in `tearDown()`.

The AppWindow smoke test also:

- closes and schedules the window for deletion in `finally`.
- disposes and resets the main DB engine cache.
- clears cached settings.
- removes the temporary runtime directory.

No production sales UI behavior was removed or hidden.

The CI and release workflow test command remains:

`python -m unittest discover -s tests -p "test*.py" -t .`

## F. Tests / Verification

Verification commands run:

- `python -m unittest tests.test_smoke` - passed, 3 tests.
- `python -m unittest tests.test_app_window_attendance_sync tests.test_reporting_refresh tests.test_history_delete_actions tests.test_history_search_suggestions tests.test_history_datetime_actions` - passed, 19 tests.
- `python -m unittest discover -s tests -p "test*.py" -t .` - passed, 407 tests.
- `python -m compileall core modules tests shell` - passed with exit code 0.

Notes:

- The full test suite still prints expected diagnostic/update-service logs from mocked failure tests.
- `compileall` reported a few cleaned-up temporary test directories as not listable, but completed successfully.

## G. Caveats

This fix intentionally changes only the smoke test setup and cleanup. It does not change:

- sales business logic
- database schema
- transaction history reload behavior
- CI test command shape
- application runtime behavior

If future UI smoke tests instantiate real pages that auto-query the database, they should follow the same pattern: isolate runtime paths, reset cached settings/engine, and call `core.db.init_db()` before constructing the page.
