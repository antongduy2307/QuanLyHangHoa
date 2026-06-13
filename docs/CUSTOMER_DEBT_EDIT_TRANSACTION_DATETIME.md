# Customer Debt Edit Transaction Datetime

## A. Files inspected

- `modules/customer/ui/customer_dialog.py`
- `modules/customer/ui/customer_detail_popup.py`
- `modules/customer/ui/customer_list_view.py`
- `modules/customer/ui/debt_payment_dialog.py`
- `modules/customer/controller.py`
- `modules/customer/service.py`
- `modules/customer/repository.py`
- `modules/customer/models.py`
- `tests/test_customer_service.py`
- `tests/test_customer_ui.py`
- `tests/test_customer_history.py`
- `tests/test_sales_service.py`

Files changed:

- `modules/customer/ui/customer_dialog.py`
- `modules/customer/ui/customer_detail_popup.py`
- `modules/customer/ui/customer_list_view.py`
- `modules/customer/controller.py`
- `modules/customer/service.py`
- `tests/test_customer_service.py`
- `tests/test_customer_ui.py`
- `tests/test_customer_history.py`
- `docs/CUSTOMER_DEBT_EDIT_TRANSACTION_DATETIME.md`

## B. Current behavior/root cause

The separate debt-payment dialog already supported a selectable payment datetime and passed it through `CustomerController.pay_debt` to `CustomerService.pay_debt`.

The missing path was the customer general-information edit dialog:

- `CustomerDialog` allowed the user to directly edit `current_balance`.
- Both customer detail views passed the edited balance to `CustomerController.update_customer`.
- `CustomerController.update_customer` called `CustomerService.update_customer` without a transaction datetime.
- When the balance changed, the service created a `BALANCE_ADJUSTMENT` ledger. For customers with transaction history, `_append_balance_ledger` therefore used its existing `datetime.now()` fallback.

Customer balance recomputation was already chronological through:

1. `transaction_datetime ASC`
2. `display_order ASC`
3. `id ASC`

## C. UI change

In customer edit mode, `CustomerDialog` now includes:

- Label: `Ngày giờ giao dịch`
- Widget: `QDateTimeEdit`
- Default: current local datetime
- Display format: `dd/MM/yyyy HH:mm`
- Calendar popup enabled

The field is edit-only. New-customer creation remains unchanged.

The dialog payload includes `balance_transaction_datetime`. Invalid date/time input is blocked with:

`Vui lòng chọn ngày giờ giao dịch công nợ.`

## D. Controller/service change

Both customer general-information edit entry points now pass the selected datetime to `CustomerController.update_customer`.

The controller forwards it as `balance_transaction_datetime` to `CustomerService.update_customer`.

The service:

- validates an explicitly supplied value is a Python `datetime`;
- uses it as the `BALANCE_ADJUSTMENT.transaction_datetime`;
- keeps backward compatibility when callers omit it.

Existing fallback behavior remains:

- callers that omit datetime still work;
- an adjustment without previous trade/debt history still uses the existing opening-balance timestamp behavior;
- an adjustment with history and no supplied datetime still falls back to current time.

Invoice-generated payment and debt-payment APIs were not changed.

## E. Balance recomputation behavior

After inserting the balance adjustment, the existing `_recompute_customer_balance` path still runs.

If the selected datetime places the adjustment between older and newer ledger rows, all `balance_after` snapshots are recomputed in chronological order. The final customer balance remains equal to the target balance entered in the general-information dialog.

No raw SQL or direct UI database update was introduced.

## F. History display behavior

Customer debt history already reads `effective_transaction_datetime` from ledger rows and displays it newest-first.

Because the adjustment ledger now stores the selected datetime:

- the history model returns that datetime;
- the existing history table displays it;
- newest-first presentation remains unchanged;
- chronological balance calculation remains independent from display ordering.

## G. Tests/verification

Added coverage for:

- edit dialog date/time field and label;
- current-time default;
- `dd/MM/yyyy HH:mm` format and calendar popup;
- selected datetime passed from the general-information UI to the controller;
- selected datetime stored on `BALANCE_ADJUSTMENT`;
- chronological recomputation of later ledger balances;
- backward-compatible service calls without explicit datetime;
- friendly rejection of invalid datetime values;
- history model and table datetime display.

Verification passed:

- `python -m unittest tests.test_customer_service` — 38 tests
- `python -m unittest tests.test_customer_ui` — 9 tests
- `python -m unittest tests.test_customer_history` — 9 tests
- `python -m unittest tests.test_sales_service` — 33 tests
- `python -m unittest discover -s tests -p "test*.py" -t .` — 519 tests
- `python -m compileall core modules tests shell`

## H. Caveats

- Datetimes remain timezone-naive local datetimes, matching the existing application convention.
- The selected datetime only creates a ledger event when the edited balance actually changes.
- Invoice, return, customer balance formulas, and invoice-generated payment datetime behavior were intentionally left unchanged.
