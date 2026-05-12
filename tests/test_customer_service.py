from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.db import Base
from core.exceptions import NotFoundError, ValidationError
from modules.customer.models import Customer
from modules.customer.repository import CustomerRepository
from modules.customer.service import CustomerService
import modules.inventory.models  # noqa: F401
import modules.returns.models  # noqa: F401
import modules.sales.models  # noqa: F401


class CustomerServiceTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = create_engine("sqlite+pysqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine, expire_on_commit=False, autoflush=False)
        self.repository = CustomerRepository(self.Session)
        self.service = CustomerService(self.repository)
        self.customer_id = self._create_customer("Khach A")

    def tearDown(self) -> None:
        self.repository.session.close()
        self.engine.dispose()

    def _create_customer(self, name: str) -> int:
        customer = Customer(customer_name=name, phone=None, address=None, current_balance=Decimal("0"), total_sales=Decimal("0"))
        self.repository.session.add(customer)
        self.repository.session.commit()
        return customer.id

    def test_create_customer_with_address(self) -> None:
        customer = self.service.create_customer(customer_name="Khach B", phone="0901", address="123 Duong A")
        self.assertEqual(customer.address, "123 Duong A")
        self.assertEqual(customer.current_balance, Decimal("0"))

    def test_create_customer_persists_optional_note(self) -> None:
        customer = self.service.create_customer(customer_name="Khach note", note="Khach VIP")
        reloaded = self.service.get_customer(customer.id)

        self.assertEqual(customer.note, "Khach VIP")
        self.assertEqual(reloaded.note, "Khach VIP")

    def test_create_customer_with_initial_balance(self) -> None:
        customer = self.service.create_customer(customer_name="Khach C", initial_balance=Decimal("120"))
        ledgers = list(self.repository.list_ledgers_by_event_type(customer.id, "OPENING_BALANCE"))

        self.assertEqual(customer.current_balance, Decimal("120"))
        self.assertEqual(customer.total_sales, Decimal("0"))
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].amount_delta, Decimal("120"))
        self.assertEqual(ledgers[0].ref_type, "OPENING_BALANCE")

    def test_editing_address(self) -> None:
        customer = self.service.update_customer(
            self.customer_id,
            customer_name="Khach A",
            phone=None,
            address="45 Le Loi",
            target_balance=Decimal("0"),
        )
        self.assertEqual(customer.address, "45 Le Loi")

    def test_update_customer_note_can_save_and_clear(self) -> None:
        updated = self.service.update_customer(
            self.customer_id,
            customer_name="Khach A",
            phone=None,
            address=None,
            note="Ghi chu moi",
            target_balance=Decimal("0"),
        )
        self.assertEqual(updated.note, "Ghi chu moi")

        cleared = self.service.update_customer(
            self.customer_id,
            customer_name="Khach A",
            phone=None,
            address=None,
            note=None,
            target_balance=Decimal("0"),
        )
        self.assertIsNone(cleared.note)

    def test_delete_unused_customer_succeeds(self) -> None:
        customer = self.service.create_customer(customer_name="Khach xoa")

        self.service.delete_customer(customer.id)

        with self.assertRaises(NotFoundError):
            self.service.get_customer(customer.id)
        remaining_ids = {row.id for row in self.service.list_customers()}
        self.assertNotIn(customer.id, remaining_ids)

    def test_delete_customer_with_history_deactivates_and_preserves_history(self) -> None:
        self.service.adjust_balance(self.customer_id, Decimal("40"), "invoice", 100, note="Phat sinh cong no")

        result = self.service.delete_customer(self.customer_id)

        self.assertEqual(result.action, "deactivated")
        remaining_ids = {row.id for row in self.service.list_customers()}
        self.assertNotIn(self.customer_id, remaining_ids)
        all_ids = {row.id for row in self.service.list_customers(include_inactive=True)}
        self.assertIn(self.customer_id, all_ids)
        self.assertFalse(self.service.get_customer(self.customer_id).is_active)
        self.assertEqual(len(self.repository.list_ledgers_by_ref(self.customer_id, "invoice", 100)), 1)

    def test_balance_adjustment_path_keeps_ledger_semantics(self) -> None:
        self.service.update_customer(
            self.customer_id,
            customer_name="Khach A",
            phone=None,
            address=None,
            target_balance=Decimal("80"),
        )
        customer = self.service.get_customer(self.customer_id)
        ledgers = list(self.repository.list_ledgers_by_event_type(self.customer_id, "BALANCE_ADJUSTMENT"))

        self.assertEqual(customer.current_balance, Decimal("80"))
        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].amount_delta, Decimal("80"))
        self.assertEqual(ledgers[0].balance_after, Decimal("80"))
        self.assertEqual(ledgers[0].ref_type, "BALANCE_ADJUSTMENT")

    def test_balance_adjustment_does_not_change_total_sales(self) -> None:
        self.service.increase_sales(self.customer_id, Decimal("120"))
        self.service.update_customer(
            self.customer_id,
            customer_name="Khach A",
            phone=None,
            address=None,
            target_balance=Decimal("50"),
        )
        customer = self.service.get_customer(self.customer_id)
        self.assertEqual(customer.total_sales, Decimal("120"))

    def test_increase_balance_creates_ledger_and_updates_balance(self) -> None:
        ledger = self.service.adjust_balance(self.customer_id, Decimal("100"), "invoice", 1, note="Cong no")
        customer = self.service.get_customer(self.customer_id)

        self.assertEqual(ledger.amount_delta, Decimal("100"))
        self.assertEqual(ledger.balance_after, Decimal("100"))
        self.assertEqual(customer.current_balance, Decimal("100"))

    def test_decrease_balance_updates_balance(self) -> None:
        self.service.adjust_balance(self.customer_id, Decimal("100"), "invoice", 1)
        ledger = self.service.adjust_balance(self.customer_id, Decimal("-30"), "payment", 2)
        customer = self.service.get_customer(self.customer_id)

        self.assertEqual(ledger.amount_delta, Decimal("-30"))
        self.assertEqual(ledger.balance_after, Decimal("70"))
        self.assertEqual(customer.current_balance, Decimal("70"))

    def test_balance_can_go_negative(self) -> None:
        ledger = self.service.adjust_balance(self.customer_id, Decimal("-50"), "payment", 3)
        customer = self.service.get_customer(self.customer_id)

        self.assertEqual(ledger.balance_after, Decimal("-50"))
        self.assertEqual(customer.current_balance, Decimal("-50"))

    def test_pay_debt_reduces_positive_balance(self) -> None:
        self.service.adjust_balance(self.customer_id, Decimal("200"), "invoice", 1)
        ledger = self.service.pay_debt(self.customer_id, Decimal("50"))
        customer = self.service.get_customer(self.customer_id)

        self.assertEqual(ledger.event_type, "DEBT_PAYMENT")
        self.assertEqual(ledger.ref_type, "DEBT_PAYMENT")
        self.assertEqual(ledger.amount_delta, Decimal("-50"))
        self.assertEqual(customer.current_balance, Decimal("150"))

    def test_pay_debt_can_make_balance_negative_on_overpayment(self) -> None:
        self.service.adjust_balance(self.customer_id, Decimal("40"), "invoice", 2)
        self.service.pay_debt(self.customer_id, Decimal("100"))
        customer = self.service.get_customer(self.customer_id)
        self.assertEqual(customer.current_balance, Decimal("-60"))

    def test_pay_debt_creates_ledger_with_correct_semantics(self) -> None:
        ledger = self.service.pay_debt(self.customer_id, Decimal("25"), note="Khach tra no")
        self.assertEqual(ledger.event_type, "DEBT_PAYMENT")
        self.assertEqual(ledger.ref_type, "DEBT_PAYMENT")
        self.assertEqual(ledger.amount_delta, Decimal("-25"))
        self.assertEqual(ledger.note, "Khach tra no")

    def test_pay_debt_generates_distinct_reference_ids_for_rapid_payments(self) -> None:
        first = self.service.pay_debt(self.customer_id, Decimal("25"))
        second = self.service.pay_debt(self.customer_id, Decimal("5"))

        self.assertNotEqual(first.ref_id, second.ref_id)
        self.assertEqual(len(self.repository.list_ledgers_by_ref(self.customer_id, "DEBT_PAYMENT", first.ref_id)), 1)
        self.assertEqual(len(self.repository.list_ledgers_by_ref(self.customer_id, "DEBT_PAYMENT", second.ref_id)), 1)

    def test_pay_debt_stores_business_transaction_datetime(self) -> None:
        payment_datetime = datetime(2026, 4, 10, 9, 45, 0)
        ledger = self.service.pay_debt(self.customer_id, Decimal("25"), payment_datetime=payment_datetime)

        self.assertEqual(ledger.transaction_datetime, payment_datetime)
        self.assertEqual(ledger.effective_transaction_datetime, payment_datetime)

    def test_pay_debt_does_not_change_total_sales(self) -> None:
        self.service.increase_sales(self.customer_id, Decimal("120"))
        self.service.pay_debt(self.customer_id, Decimal("30"))
        customer = self.service.get_customer(self.customer_id)
        self.assertEqual(customer.total_sales, Decimal("120"))

    def test_update_debt_payment_changes_balance_correctly(self) -> None:
        ledger = self.service.pay_debt(self.customer_id, Decimal("25"), note="Cu")
        updated = self.service.update_debt_payment(ledger.id, Decimal("40"), note="Moi")
        customer = self.service.get_customer(self.customer_id)
        original_ledgers = list(self.repository.list_ledgers_by_ref(self.customer_id, "DEBT_PAYMENT", ledger.ref_id))

        self.assertEqual(updated.event_type, "DEBT_PAYMENT")
        self.assertEqual(updated.amount_delta, Decimal("-40"))
        self.assertEqual(customer.current_balance, Decimal("-40"))
        self.assertEqual(len(original_ledgers), 3)
        self.assertTrue(any(entry.event_type == "DEBT_PAYMENT_EDIT_ROLLBACK" and entry.amount_delta == Decimal("25") for entry in original_ledgers))

    def test_update_debt_payment_does_not_change_total_sales(self) -> None:
        self.service.increase_sales(self.customer_id, Decimal("120"))
        ledger = self.service.pay_debt(self.customer_id, Decimal("20"))
        self.service.update_debt_payment(ledger.id, Decimal("35"), note="Sua")
        customer = self.service.get_customer(self.customer_id)
        self.assertEqual(customer.total_sales, Decimal("120"))

    def test_update_debt_payment_note_works(self) -> None:
        ledger = self.service.pay_debt(self.customer_id, Decimal("25"), note="Cu")
        updated = self.service.update_debt_payment(ledger.id, Decimal("25"), note="Ghi chu moi")
        self.assertEqual(updated.note, "Ghi chu moi")

    def test_update_debt_payment_keeps_original_transaction_datetime_by_default(self) -> None:
        payment_datetime = datetime(2026, 4, 10, 8, 30, 0)
        ledger = self.service.pay_debt(self.customer_id, Decimal("25"), payment_datetime=payment_datetime)

        updated = self.service.update_debt_payment(ledger.id, Decimal("30"), note="Sua")

        self.assertEqual(updated.transaction_datetime, payment_datetime)

    def test_update_debt_payment_can_change_transaction_datetime(self) -> None:
        original_datetime = datetime(2026, 4, 10, 8, 30, 0)
        new_datetime = datetime(2026, 4, 10, 11, 15, 0)
        ledger = self.service.pay_debt(self.customer_id, Decimal("25"), payment_datetime=original_datetime)

        updated = self.service.update_debt_payment(ledger.id, Decimal("30"), note="Sua", payment_datetime=new_datetime)

        self.assertEqual(updated.transaction_datetime, new_datetime)

    def test_update_debt_payment_datetime_changes_business_datetime_only(self) -> None:
        ledger = self.service.pay_debt(self.customer_id, Decimal("25"), payment_datetime=datetime(2026, 4, 10, 8, 30, 0))
        original_amount = ledger.amount_delta
        original_balance = self.service.get_customer(self.customer_id).current_balance

        updated = self.service.update_debt_payment_datetime(ledger.id, datetime(2026, 4, 10, 12, 45, 0))

        latest_ledgers = list(self.repository.list_ledgers_by_ref(self.customer_id, "DEBT_PAYMENT", ledger.ref_id))
        customer = self.service.get_customer(self.customer_id)
        self.assertEqual(updated.effective_transaction_datetime, datetime(2026, 4, 10, 12, 45, 0))
        self.assertTrue(all(entry.effective_transaction_datetime == datetime(2026, 4, 10, 12, 45, 0) for entry in latest_ledgers))
        self.assertTrue(all(entry.amount_delta == original_amount for entry in latest_ledgers))
        self.assertEqual(customer.current_balance, original_balance)
        self.assertEqual(customer.total_sales, Decimal("0"))

    def test_delete_debt_payment_removes_all_ledgers_for_reference_and_restores_balance(self) -> None:
        self.service.adjust_balance(self.customer_id, Decimal("100"), "invoice", 1)
        ledger = self.service.pay_debt(self.customer_id, Decimal("25"), note="Cu")
        updated = self.service.update_debt_payment(ledger.id, Decimal("40"), note="Moi")

        self.service.delete_debt_payment(updated.id)

        customer = self.service.get_customer(self.customer_id)
        self.assertEqual(customer.current_balance, Decimal("100"))
        self.assertEqual(self.repository.list_ledgers_by_ref(self.customer_id, "DEBT_PAYMENT", ledger.ref_id), [])

    def test_delete_debt_payment_recomputes_later_balance_snapshots_without_changing_timestamps(self) -> None:
        first_datetime = datetime(2026, 4, 10, 9, 0, 0)
        payment_datetime = datetime(2026, 4, 10, 10, 0, 0)
        later_datetime = datetime(2026, 4, 10, 11, 0, 0)
        self.service.adjust_balance(self.customer_id, Decimal("100"), "INVOICE", 1, transaction_datetime=first_datetime)
        payment = self.service.pay_debt(self.customer_id, Decimal("30"), payment_datetime=payment_datetime)
        later = self.service.adjust_balance(self.customer_id, Decimal("50"), "INVOICE", 2, transaction_datetime=later_datetime)

        self.service.delete_debt_payment(payment.id)

        customer = self.service.get_customer(self.customer_id)
        later_ledgers = self.repository.list_ledgers_by_ref(self.customer_id, "INVOICE", 2)
        self.assertEqual(customer.current_balance, Decimal("150"))
        self.assertEqual(later_ledgers[0].id, later.id)
        self.assertEqual(later_ledgers[0].transaction_datetime, later_datetime)
        self.assertEqual(later_ledgers[0].balance_after, Decimal("150"))

    def test_update_debt_payment_invalid_amount_fails(self) -> None:
        ledger = self.service.pay_debt(self.customer_id, Decimal("25"))
        with self.assertRaises(ValidationError):
            self.service.update_debt_payment(ledger.id, Decimal("0"))
        with self.assertRaises(ValidationError):
            self.service.update_debt_payment(ledger.id, Decimal("-10"))

    def test_update_debt_payment_invalid_or_nonexistent_ref_fails(self) -> None:
        self.service.adjust_balance(self.customer_id, Decimal("10"), "MANUAL", 999, event_type="MANUAL")
        manual_ledger = self.repository.list_ledgers_by_ref(self.customer_id, "MANUAL", 999)[0]
        with self.assertRaises(ValidationError):
            self.service.update_debt_payment(manual_ledger.id, Decimal("20"))
        with self.assertRaises(NotFoundError):
            self.service.update_debt_payment(999999, Decimal("20"))

    def test_pay_debt_invalid_amount_fails(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.pay_debt(self.customer_id, Decimal("0"))
        with self.assertRaises(ValidationError):
            self.service.pay_debt(self.customer_id, Decimal("-10"))

    def test_rollback_balance_reverses_reference_and_creates_rollback_ledger(self) -> None:
        self.service.adjust_balance(self.customer_id, Decimal("120"), "invoice", 10)
        rollback_ledger = self.service.rollback_balance(self.customer_id, "invoice", 10)
        customer = self.service.get_customer(self.customer_id)

        self.assertEqual(rollback_ledger.event_type, "ROLLBACK")
        self.assertEqual(rollback_ledger.amount_delta, Decimal("-120"))
        self.assertEqual(rollback_ledger.balance_after, Decimal("0"))
        self.assertEqual(customer.current_balance, Decimal("0"))

    def test_rollback_twice_fails(self) -> None:
        self.service.adjust_balance(self.customer_id, Decimal("75"), "invoice", 11)
        self.service.rollback_balance(self.customer_id, "invoice", 11)
        with self.assertRaises(ValidationError):
            self.service.rollback_balance(self.customer_id, "invoice", 11)

    def test_rollback_without_ledger_fails(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.rollback_balance(self.customer_id, "invoice", 999)

    def test_ledger_rows_are_created_correctly(self) -> None:
        self.service.adjust_balance(self.customer_id, Decimal("40"), "invoice", 100, note="Nhap cong no")
        self.service.adjust_balance(self.customer_id, Decimal("-10"), "payment", 101, note="Khach tra")
        ledgers = list(self.repository.list_ledgers_by_ref(self.customer_id, "invoice", 100))
        payment_ledgers = list(self.repository.list_ledgers_by_ref(self.customer_id, "payment", 101))

        self.assertEqual(len(ledgers), 1)
        self.assertEqual(ledgers[0].note, "Nhap cong no")
        self.assertEqual(payment_ledgers[0].amount_delta, Decimal("-10"))

    def test_adjust_balance_rejects_zero_amount(self) -> None:
        with self.assertRaises(ValidationError):
            self.service.adjust_balance(self.customer_id, Decimal("0"), "invoice", 1)

    def test_increase_sales_accumulates_total_sales(self) -> None:
        self.service.increase_sales(self.customer_id, Decimal("50"))
        self.service.increase_sales(self.customer_id, Decimal("25"))
        customer = self.service.get_customer(self.customer_id)
        self.assertEqual(customer.total_sales, Decimal("75"))


if __name__ == "__main__":
    unittest.main()


