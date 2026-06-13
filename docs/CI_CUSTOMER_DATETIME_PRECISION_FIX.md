# CI Customer Datetime Precision Fix

## Root cause

The customer debt edit field correctly defaults to the current local datetime:

```python
selected_datetime = balance_transaction_datetime or datetime.now()
self.balance_transaction_datetime_input = QDateTimeEdit(QDateTime(selected_datetime))
```

Python `datetime.now()` includes microsecond precision. Qt's `QDateTime` and
`QDateTimeEdit` preserve time to millisecond precision, so converting the value
back with `toPyDateTime()` can truncate the final three microsecond digits.

In the CI failure:

- Python `before`: `2026-06-13 08:47:15.677345`
- Qt `selected`: `2026-06-13 08:47:15.677000`

The selected value was only 345 microseconds earlier. The production default
was correct; the strict `before <= selected` assertion was too precise.

## Files changed

- `tests/test_customer_ui.py`
- `docs/CI_CUSTOMER_DATETIME_PRECISION_FIX.md`

No production files were changed.

## Exact test adjustment

The test still verifies:

- the `QDateTimeEdit` exists;
- the `Ngày giờ giao dịch` label exists;
- the display format and calendar popup remain configured;
- the selected datetime is within one second of the captured current time;
- the selected datetime is not later than the `after` timestamp.

The precision-sensitive assertion:

```python
self.assertLessEqual(before, selected)
```

was replaced with:

```python
self.assertLessEqual(abs((selected - before).total_seconds()), 1.0)
```

The existing upper-bound assertion remains:

```python
self.assertLessEqual(selected, after)
```

This allows Qt's expected sub-millisecond truncation without accepting an
arbitrary old/default date.

## Verification

Passed:

- Focused CI test: 1 test
- `tests.test_customer_ui`: 9 tests
- Full unittest discovery: 519 tests
- `python -m compileall core modules tests shell`

No warnings or logs were suppressed.
