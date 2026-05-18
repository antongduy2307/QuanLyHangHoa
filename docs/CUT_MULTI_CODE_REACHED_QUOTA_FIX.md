# CUT Multi-Code Reached-Quota Fix

## A. Files changed

- `modules/attendance/cut_bonus.py`
- `tests/test_attendance_day_entry.py`
- `docs/CUT_MULTI_CODE_REACHED_QUOTA_FIX.md`

## B. Previous behavior

The CUT employee bonus helper already used the tiered multi-code formula with Decimal values:

- No active code rows: bonus `0`.
- Total quantity less than or equal to the average quota: bonus `0`.
- No code reaches its own quota but total exceeds average quota: split-quota rule, using `quota / active_code_count` per code.
- One or more codes reach their own quota: every reached code was paid only on `quantity - quota`, while below-quota codes were paid on their full actual quantity.

That last branch was incorrect when two or more product codes reached quota because it subtracted quota from every reached code.

## C. New reached-quota rule

After the existing average-quota zero guard, the helper now counts active codes where:

`quantity >= quota_quantity`

If two or more active codes reached quota:

- exactly one reached code has quota charged/subtracted;
- every other reached code is paid on full actual quantity;
- below-quota active codes keep the existing behavior and are paid on full actual quantity.

If fewer than two codes reached quota, the previous one-reached and no-reached branches remain unchanged.

## D. Lowest-price selection rule

Among reached codes, the quota-charged code is the reached code with the lowest `excess_unit_price`.

For that selected code:

`amount = max(0, quantity - quota_quantity) * excess_unit_price`

For every other active code in the two-or-more-reached branch:

`amount = quantity * excess_unit_price`

The code is selected by lowest price, not by lowest quantity.

## E. Tie rule

If multiple reached codes share the same lowest `excess_unit_price`, the first matching item in the input order is selected as the quota-charged code.

The implementation preserves deterministic tie behavior by using the original active item order.

## F. Decimal handling

- All values continue to be converted with `Decimal(str(value))` or passed through as `Decimal`.
- No float conversion was introduced.
- Decimal quota and quantity values are preserved through intermediate calculations.
- Final integer VND storage behavior is unchanged and still happens outside the helper through the existing save/preview quantization paths.

## G. Tests/verification

Added focused CUT bonus tests for:

- two reached codes where the lower-price code is exactly at quota;
- two reached codes where the lower-price code exceeds quota;
- lowest price winning over lowest quantity;
- three reached codes;
- tied lowest price choosing the first input item;
- decimal quota with multiple reached codes;
- existing one-reached and no-reached cases.

Regression verification run:

- `python -m unittest tests.test_attendance_day_entry`
- `python -m unittest tests.test_attendance_report`
- `python -m unittest tests.test_attendance_inventory_integration`
- `python -m unittest discover -s tests -p "test*.py" -t .`
- `python -m compileall core modules tests shell`

## H. Caveats

- BLOW normal work formulas were not changed.
- BLOW extra CUT/VK formula was not changed.
- Inventory effect logic, product sync logic, and UI layout were not changed.
