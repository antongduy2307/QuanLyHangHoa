# Schema Invariants

Tai lieu nay ghi ro boundary giua DB constraint, model-local helper, va service layer.

## Enforced In DB

- Enum/check cho `unit_mode`, `unit_type`, `payment_method`, `invoice_status`, `return_handling_mode`
- `products.product_code_base` unique + indexed
- `product_prices (product_id, unit_type)` unique
- `inventory_balances` khong cho luu dong thoi ca bao va bich, va khong cho ca hai cung null
- `inventory_receipt_items.quantity > 0`
- `inventory_adjustment_items.old_quantity >= 0`, `new_quantity >= 0`
- `invoices.invoice_code` unique + indexed
- `invoices.invoice_datetime` indexed
- `invoices.customer_id` nullable cho khach le
- `invoices.paid_amount` neu co gia tri thi phai >= 0, nhung co the lon hon `total_amount`
- `invoice_items` bat buoc snapshot field co gia tri hop le o muc schema co ban
- `return_invoices.return_code` unique + indexed
- `return_invoice_items.source_invoice_item_id` la foreign key bat buoc

## Enforced By Local Model Helpers

- `Product.validate_price_unit_type(...)`
  - `unit_mode` chi xac dinh tap `unit_type` hop le o muc domain
  - `ProductPrice.is_enabled` moi la co quyet dinh don vi nao dang duoc phep ban
  - DB khong ep san pham `BAO_KG` phai luon co du ca `BAO` va `KG`
- `InventoryBalance.validate_for_product(product)`
  - `BAO_KG` chi dung `on_hand_bao_decimal`
  - `BICH` chi dung `on_hand_bich_integer`
- `InventoryAdjustmentItem.delta_quantity`
  - duoc tinh tu dong tu `new_quantity - old_quantity`

## Deferred To Service Layer

- BAO_KG chi dung ton kho chuan theo bao decimal
  - helper model co mo ta rule, nhung enforcement khi tao/sua theo flow nghiep vu se nam o service
- KG la don vi quy doi, khong luu ton rieng
  - service/reporting se quy doi theo 1 bao = 25kg
- `unit_mode` va `unit_type` hop le theo domain nhung cac rule cheo bang phuc tap duoc kiem o service
  - vi du insert dong gia hay dong hoa don cho mot product cu the
- Invoice overpayment duoc luu day du tren header `paid_amount` va ledger `INVOICE_PAYMENT`; phan du tiep tuc giam no cu
- Update/delete invoice hien tai dung ledger strategy B:
  - rollback anh huong bang cach reverse current balance tu tong ledger ref hien tai
  - xoa ledger rows cu vat ly
  - apply lai ledger moi cho trang thai cuoi cung
- Return invoice la bill rieng, khong sua invoice goc
- `STORE_CREDIT` lam giam current_balance day du theo tong gia tri return
- `REFUND_NOW` chi giam current_balance toi da den 0 trong V1; khong tao balance am chi vi refund_now
- Reporting tong he thong phai tinh truc tiep tu `invoices` / `invoice_items` / `return_invoices` / `return_invoice_items`, khong dung `customers.total_sales`
- Logic so luong tra khong vuot qua da mua duoc enforce o service
- Xoa hoa don la hard delete sau khi rollback day du ton kho / cong no / total_sales
- Moi thay doi cong no phai di qua ledger o service layer; model khong tu ghi ledger

## Dev DB Note

Chua co migration. Neu schema da thay doi, can reset DB dev sach thay vi co migrate ngam.
