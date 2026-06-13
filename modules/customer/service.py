from __future__ import annotations

from collections.abc import Sequence
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from threading import Lock
from time import time_ns

from sqlalchemy.orm import Session

from core.exceptions import ValidationError
from core.logging import get_logger
from modules.customer.dto import CustomerDTO
from modules.customer.mappers import to_dto
from modules.customer.models import Customer, CustomerBalanceLedger
from modules.customer.repository import CustomerRepository


LOGGER = get_logger(__name__)
OPENING_BALANCE_DATETIME = datetime(1900, 1, 1, 0, 0, 0)
_REF_ID_LOCK = Lock()
_LAST_GENERATED_REF_ID = 0


@dataclass(frozen=True, slots=True)
class CustomerDeleteResult:
    customer_id: int
    action: str


class CustomerService:
    def __init__(self, repository: CustomerRepository) -> None:
        self._repository = repository

    def use_session(self, session: Session) -> None:
        self._repository.use_session(session)

    def list_customers(self, *, include_inactive: bool = False) -> Sequence[CustomerDTO]:
        return [to_dto(customer) for customer in self._repository.list_customers(include_inactive=include_inactive)]

    def get_customer(self, customer_id: int) -> Customer:
        return self._repository.get_customer(customer_id)

    def get_delete_mode(self, customer_id: int) -> str:
        customer = self._repository.get_customer(customer_id)
        return "deactivate" if self._repository.has_business_history(customer.id) else "hard_delete"

    def delete_customer(self, customer_id: int) -> CustomerDeleteResult:
        session = self._repository.session
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = self._repository.get_customer(customer_id)
            if self._repository.has_business_history(customer_id):
                customer.is_active = False
                session.flush()
                return CustomerDeleteResult(customer_id=customer.id, action="deactivated")
            session.delete(customer)
            session.flush()
            return CustomerDeleteResult(customer_id=customer_id, action="hard_deleted")

    def create_customer(
        self,
        *,
        customer_name: str,
        phone: str | None = None,
        address: str | None = None,
        initial_balance: Decimal | int | str = Decimal("0"),
        note: str | None = None,
    ) -> Customer:
        session = self._repository.session
        normalized_name = self._require_text(customer_name, "customer_name")
        normalized_phone = self._normalize_optional_text(phone)
        normalized_address = self._normalize_optional_text(address)
        normalized_note = self._normalize_optional_text(note)
        normalized_initial_balance = self._to_decimal(initial_balance)
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = Customer(
                customer_name=normalized_name,
                phone=normalized_phone,
                address=normalized_address,
                note=normalized_note,
                current_balance=Decimal("0"),
                total_sales=Decimal("0"),
                is_walk_in=False,
            )
            session.add(customer)
            session.flush()
            if normalized_initial_balance != Decimal("0"):
                ledger = self._append_balance_ledger(
                    customer,
                    amount_delta=normalized_initial_balance,
                    ref_type="OPENING_BALANCE",
                    ref_id=customer.id,
                    event_type="OPENING_BALANCE",
                    note="Opening balance",
                    transaction_datetime=OPENING_BALANCE_DATETIME,
                )
                session.flush()
                self._recompute_customer_balance(customer.id, reason=f"create_customer:{ledger.id}")
            session.flush()
            return customer

    def update_customer(
        self,
        customer_id: int,
        *,
        customer_name: str,
        phone: str | None = None,
        address: str | None = None,
        note: str | None = None,
        target_balance: Decimal | int | str | None = None,
        balance_note: str | None = None,
        balance_transaction_datetime: datetime | None = None,
    ) -> Customer:
        session = self._repository.session
        normalized_name = self._require_text(customer_name, "customer_name")
        normalized_phone = self._normalize_optional_text(phone)
        normalized_address = self._normalize_optional_text(address)
        normalized_note = self._normalize_optional_text(note)
        normalized_balance_transaction_datetime = None
        if balance_transaction_datetime is not None:
            if not isinstance(balance_transaction_datetime, datetime):
                raise ValidationError("Vui lòng chọn ngày giờ giao dịch công nợ.")
            normalized_balance_transaction_datetime = balance_transaction_datetime
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = self._repository.get_customer(customer_id)
            customer.customer_name = normalized_name
            customer.phone = normalized_phone
            customer.address = normalized_address
            customer.note = normalized_note

            if target_balance is not None:
                normalized_target_balance = self._to_decimal(target_balance)
                delta = normalized_target_balance - customer.current_balance
                if delta != Decimal("0"):
                    transaction_datetime = normalized_balance_transaction_datetime
                    event_type = "BALANCE_ADJUSTMENT"
                    if transaction_datetime is None and not self._repository.has_trade_or_debt_history(customer_id):
                        transaction_datetime = OPENING_BALANCE_DATETIME
                    ledger = self._append_balance_ledger(
                        customer,
                        amount_delta=delta,
                        ref_type="BALANCE_ADJUSTMENT",
                        ref_id=self._generate_ref_id(),
                        event_type=event_type,
                        note=balance_note or "Manual balance adjustment",
                        transaction_datetime=transaction_datetime,
                    )
                    session.flush()
                    self._recompute_customer_balance(customer.id, reason=f"update_customer:{ledger.id}")
            session.flush()
            return customer

    def list_reference_ledgers(self, customer_id: int, ref_type: str, ref_id: int) -> Sequence[CustomerBalanceLedger]:
        normalized_ref_type = self._require_text(ref_type, "ref_type")
        return self._repository.list_ledgers_by_ref(customer_id, normalized_ref_type, int(ref_id))

    def remove_reference_balance_effect(self, customer_id: int, ref_type: str, ref_id: int) -> Decimal:
        session = self._repository.session
        normalized_ref_type = self._require_text(ref_type, "ref_type")
        normalized_ref_id = int(ref_id)
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = self._repository.get_customer(customer_id)
            ledgers = list(self._repository.list_ledgers_by_ref(customer_id, normalized_ref_type, normalized_ref_id))
            if not ledgers:
                raise ValidationError("No balance ledger found for the given reference.")

            net_delta = sum((ledger.amount_delta for ledger in ledgers), start=Decimal("0"))
            LOGGER.info(
                "Removing customer balance reference | customer_id=%s | ref_type=%s | ref_id=%s | ledger_ids=%s",
                customer_id,
                normalized_ref_type,
                normalized_ref_id,
                [ledger.id for ledger in ledgers],
            )
            for ledger in ledgers:
                session.delete(ledger)
            session.flush()
            self._recompute_customer_balance(customer.id, reason=f"remove_reference:{normalized_ref_type}:{normalized_ref_id}")
            return net_delta

    def remove_source_debt_payments(
        self,
        customer_id: int,
        source_ref_type: str,
        source_ref_id: int,
        *,
        legacy_note: str | None = None,
    ) -> tuple[int, ...]:
        session = self._repository.session
        normalized_source_ref_type = self._require_text(source_ref_type, "source_ref_type")
        normalized_source_ref_id = int(source_ref_id)
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            ref_ids = tuple(
                self._repository.list_debt_payment_ref_ids_by_source(
                    customer_id,
                    normalized_source_ref_type,
                    normalized_source_ref_id,
                    legacy_note=legacy_note,
                )
            )
            if not ref_ids:
                return ()
            LOGGER.info(
                "Removing source-linked debt payments | customer_id=%s | source_ref_type=%s | source_ref_id=%s | ref_ids=%s",
                customer_id,
                normalized_source_ref_type,
                normalized_source_ref_id,
                ref_ids,
            )
            for ref_id in ref_ids:
                self.remove_reference_balance_effect(customer_id, "DEBT_PAYMENT", ref_id)
            return ref_ids

    def sync_reference_transaction_datetime(
        self,
        customer_id: int,
        ref_type: str,
        ref_id: int,
        new_datetime: datetime,
        *,
        sync_source_debt_payments: bool = False,
        legacy_source_note: str | None = None,
    ) -> tuple[int, ...]:
        session = self._repository.session
        normalized_ref_type = self._require_text(ref_type, "ref_type")
        normalized_ref_id = int(ref_id)
        normalized_datetime = self._require_datetime(new_datetime, "new_datetime")
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = self._repository.get_customer(customer_id)
            updated_ids: list[int] = []
            ledgers = list(self._repository.list_ledgers_by_ref(customer_id, normalized_ref_type, normalized_ref_id))
            for ledger in ledgers:
                ledger.transaction_datetime = normalized_datetime
                updated_ids.append(ledger.id)

            if sync_source_debt_payments:
                source_ref_ids = self._repository.list_debt_payment_ref_ids_by_source(
                    customer_id,
                    normalized_ref_type,
                    normalized_ref_id,
                    legacy_note=legacy_source_note,
                )
                for debt_ref_id in source_ref_ids:
                    for ledger in self._repository.list_ledgers_by_ref(customer_id, "DEBT_PAYMENT", debt_ref_id):
                        ledger.transaction_datetime = normalized_datetime
                        updated_ids.append(ledger.id)

            if updated_ids:
                session.flush()
                self._recompute_customer_balance(customer.id, reason=f"sync_reference_datetime:{normalized_ref_type}:{normalized_ref_id}")
            return tuple(updated_ids)

    def adjust_balance(
        self,
        customer_id: int,
        amount_delta: Decimal | int | str,
        ref_type: str,
        ref_id: int,
        note: str | None = None,
        event_type: str = "ADJUSTMENT",
        transaction_datetime: datetime | None = None,
        source_ref_type: str | None = None,
        source_ref_id: int | None = None,
        display_order: int = 0,
    ) -> CustomerBalanceLedger:
        session = self._repository.session
        normalized_delta = self._require_non_zero_decimal(amount_delta, "amount_delta")
        normalized_ref_type = self._require_text(ref_type, "ref_type")
        normalized_event_type = self._require_text(event_type, "event_type")
        normalized_source_ref_type = self._normalize_optional_text(source_ref_type)
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = self._repository.get_customer(customer_id)
            ledger = self._append_balance_ledger(
                customer,
                amount_delta=normalized_delta,
                ref_type=normalized_ref_type,
                ref_id=int(ref_id),
                event_type=normalized_event_type,
                note=note,
                transaction_datetime=transaction_datetime,
                source_ref_type=normalized_source_ref_type,
                source_ref_id=source_ref_id,
                display_order=display_order,
            )
            session.flush()
            self._recompute_customer_balance(customer.id, reason=f"adjust_balance:{ledger.id}")
            LOGGER.info(
                "Customer balance adjusted | customer_id=%s | ledger_id=%s | event_type=%s | ref_type=%s | ref_id=%s | amount_delta=%s | transaction_datetime=%s",
                customer_id,
                ledger.id,
                normalized_event_type,
                normalized_ref_type,
                int(ref_id),
                normalized_delta,
                ledger.transaction_datetime,
            )
            return ledger

    def pay_debt(
        self,
        customer_id: int,
        amount: Decimal | int | str,
        note: str | None = None,
        payment_datetime: datetime | None = None,
        source_ref_type: str | None = None,
        source_ref_id: int | None = None,
        display_order: int = 30,
    ) -> CustomerBalanceLedger:
        normalized_amount = self._require_positive_decimal(amount, "amount")
        ref_id = self._generate_ref_id()
        return self.adjust_balance(
            customer_id,
            amount_delta=normalized_amount * Decimal("-1"),
            ref_type="DEBT_PAYMENT",
            ref_id=ref_id,
            note=note,
            event_type="DEBT_PAYMENT",
            transaction_datetime=payment_datetime,
            source_ref_type=source_ref_type,
            source_ref_id=source_ref_id,
            display_order=display_order,
        )

    def update_debt_payment(
        self,
        ledger_id: int,
        new_amount: Decimal | int | str,
        note: str | None = None,
        payment_datetime: datetime | None = None,
    ) -> CustomerBalanceLedger:
        session = self._repository.session
        normalized_amount = self._require_positive_decimal(new_amount, "new_amount")
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            original_ledger = self._repository.get_ledger(ledger_id)
            if original_ledger.event_type != "DEBT_PAYMENT" or original_ledger.ref_type != "DEBT_PAYMENT":
                raise ValidationError("Giao dịch được chọn không phải là giao dịch trả nợ hợp lệ.")
            customer = self._repository.get_customer(original_ledger.customer_id)
            effective_payment_datetime = payment_datetime or original_ledger.effective_transaction_datetime

            rollback_amount = original_ledger.amount_delta * Decimal("-1")
            self._append_balance_ledger(
                customer,
                amount_delta=rollback_amount,
                ref_type="DEBT_PAYMENT",
                ref_id=original_ledger.ref_id,
                event_type="DEBT_PAYMENT_EDIT_ROLLBACK",
                note=f"Rollback debt payment {original_ledger.ref_id}",
                transaction_datetime=effective_payment_datetime,
                source_ref_type=original_ledger.source_ref_type,
                source_ref_id=original_ledger.source_ref_id,
                display_order=original_ledger.display_order,
            )
            replacement = self._append_balance_ledger(
                customer,
                amount_delta=normalized_amount * Decimal("-1"),
                ref_type="DEBT_PAYMENT",
                ref_id=original_ledger.ref_id,
                event_type="DEBT_PAYMENT",
                note=note,
                transaction_datetime=effective_payment_datetime,
                source_ref_type=original_ledger.source_ref_type,
                source_ref_id=original_ledger.source_ref_id,
                display_order=original_ledger.display_order,
            )
            session.flush()
            self._recompute_customer_balance(customer.id, reason=f"update_debt_payment:{original_ledger.ref_id}")
            LOGGER.info(
                "Debt payment updated | customer_id=%s | ref_id=%s | original_ledger_id=%s | replacement_ledger_id=%s | new_amount=%s | transaction_datetime=%s",
                customer.id,
                original_ledger.ref_id,
                original_ledger.id,
                replacement.id,
                normalized_amount,
                effective_payment_datetime,
            )
            return replacement

    def increase_sales(self, customer_id: int, amount: Decimal | int | str) -> Customer:
        session = self._repository.session
        normalized_amount = self._require_non_negative_decimal(amount, "amount")
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = self._repository.get_customer(customer_id)
            customer.total_sales = customer.total_sales + normalized_amount
            session.flush()
            return customer

    def decrease_sales(self, customer_id: int, amount: Decimal | int | str) -> Customer:
        session = self._repository.session
        normalized_amount = self._require_non_negative_decimal(amount, "amount")
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = self._repository.get_customer(customer_id)
            updated_total = customer.total_sales - normalized_amount
            if updated_total < Decimal("0"):
                raise ValidationError("total_sales cannot become negative.")
            customer.total_sales = updated_total
            session.flush()
            return customer

    def rollback_balance(self, customer_id: int, ref_type: str, ref_id: int) -> CustomerBalanceLedger:
        session = self._repository.session
        normalized_ref_type = self._require_text(ref_type, "ref_type")
        normalized_ref_id = int(ref_id)
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = self._repository.get_customer(customer_id)
            ledgers = list(self._repository.list_ledgers_by_ref(customer_id, normalized_ref_type, normalized_ref_id))
            if any(ledger.event_type == "ROLLBACK" for ledger in ledgers):
                raise ValidationError("Balance for this reference has already been rolled back.")

            original_ledgers = [ledger for ledger in ledgers if ledger.event_type != "ROLLBACK"]
            if not original_ledgers:
                raise ValidationError("No balance ledger found for the given reference.")

            original_sum = sum((ledger.amount_delta for ledger in original_ledgers), start=Decimal("0"))
            if original_sum == Decimal("0"):
                raise ValidationError("Balance ledger sum is zero; nothing to roll back.")

            amount_to_reverse = original_sum * Decimal("-1")
            rollback_ledger = self._append_balance_ledger(
                customer,
                amount_delta=amount_to_reverse,
                ref_type=normalized_ref_type,
                ref_id=normalized_ref_id,
                event_type="ROLLBACK",
                note=f"Rollback for {normalized_ref_type}:{normalized_ref_id}",
            )
            session.flush()
            self._recompute_customer_balance(customer.id, reason=f"rollback_balance:{normalized_ref_type}:{normalized_ref_id}")
            return rollback_ledger

    def update_debt_payment_datetime(self, ledger_id: int, new_datetime: datetime) -> CustomerBalanceLedger:
        session = self._repository.session
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            normalized_datetime = self._require_datetime(new_datetime, "new_datetime")
            ledger = self._repository.get_ledger(ledger_id)
            if ledger.event_type != "DEBT_PAYMENT" or ledger.ref_type != "DEBT_PAYMENT":
                raise ValidationError("Giao dịch được chọn không phải là giao dịch trả nợ hợp lệ.")
            ledgers = list(self._repository.list_ledgers_by_ref(ledger.customer_id, "DEBT_PAYMENT", ledger.ref_id))
            if not ledgers:
                raise ValidationError("Không tìm thấy giao dịch trả nợ để cập nhật.")
            for entry in ledgers:
                entry.transaction_datetime = normalized_datetime
            session.flush()
            self._recompute_customer_balance(ledger.customer_id, reason=f"update_debt_payment_datetime:{ledger.ref_id}")
            LOGGER.info(
                "Debt payment datetime updated | customer_id=%s | ref_id=%s | ledger_ids=%s | new_datetime=%s",
                ledger.customer_id,
                ledger.ref_id,
                [entry.id for entry in ledgers],
                normalized_datetime,
            )
            return ledger

    def delete_debt_payment(self, ledger_id: int) -> None:
        session = self._repository.session
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            ledger = self._repository.get_ledger(ledger_id)
            if ledger.event_type != "DEBT_PAYMENT" or ledger.ref_type != "DEBT_PAYMENT":
                raise ValidationError("Giao dịch được chọn không phải là giao dịch trả nợ hợp lệ.")
            LOGGER.info(
                "Deleting debt payment | customer_id=%s | selected_ledger_id=%s | ref_id=%s | transaction_datetime=%s",
                ledger.customer_id,
                ledger.id,
                ledger.ref_id,
                ledger.transaction_datetime,
            )
            self.remove_reference_balance_effect(ledger.customer_id, "DEBT_PAYMENT", ledger.ref_id)

    def _append_balance_ledger(
        self,
        customer: Customer,
        *,
        amount_delta: Decimal,
        ref_type: str,
        ref_id: int,
        event_type: str,
        note: str | None,
        transaction_datetime: datetime | None = None,
        source_ref_type: str | None = None,
        source_ref_id: int | None = None,
        display_order: int = 0,
    ) -> CustomerBalanceLedger:
        balance_after = customer.current_balance + amount_delta
        customer.current_balance = balance_after
        ledger = CustomerBalanceLedger(
            customer_id=customer.id,
            event_type=event_type,
            ref_type=ref_type,
            ref_id=int(ref_id),
            source_ref_type=source_ref_type,
            source_ref_id=None if source_ref_id is None else int(source_ref_id),
            display_order=int(display_order),
            amount_delta=amount_delta,
            balance_after=balance_after,
            transaction_datetime=transaction_datetime or datetime.now(),
            note=note,
        )
        self._repository.session.add(ledger)
        return ledger

    def _recompute_customer_balance(self, customer_id: int, *, reason: str) -> Decimal:
        customer = self._repository.get_customer(customer_id)
        running_balance = Decimal("0")
        ledgers = list(self._repository.list_balance_ledgers_by_customer(customer_id))
        for ledger in ledgers:
            running_balance += ledger.amount_delta
            ledger.balance_after = running_balance
        customer.current_balance = running_balance
        LOGGER.info(
            "Customer balance recomputed | customer_id=%s | reason=%s | ledger_count=%s | current_balance=%s",
            customer_id,
            reason,
            len(ledgers),
            running_balance,
        )
        return running_balance

    @staticmethod
    def _generate_ref_id() -> int:
        global _LAST_GENERATED_REF_ID
        with _REF_ID_LOCK:
            candidate = time_ns()
            if candidate <= _LAST_GENERATED_REF_ID:
                candidate = _LAST_GENERATED_REF_ID + 1
            _LAST_GENERATED_REF_ID = candidate
            return candidate

    @staticmethod
    def _to_decimal(value: Decimal | int | str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        normalized = (value or "").strip()
        return normalized or None

    def _require_non_zero_decimal(self, value: Decimal | int | str, field_name: str) -> Decimal:
        normalized = self._to_decimal(value)
        if normalized == Decimal("0"):
            raise ValidationError(f"{field_name} must not be 0.")
        return normalized

    def _require_positive_decimal(self, value: Decimal | int | str, field_name: str) -> Decimal:
        normalized = self._to_decimal(value)
        if normalized <= Decimal("0"):
            raise ValidationError(f"{field_name} must be > 0.")
        return normalized

    def _require_non_negative_decimal(self, value: Decimal | int | str, field_name: str) -> Decimal:
        normalized = self._to_decimal(value)
        if normalized < Decimal("0"):
            raise ValidationError(f"{field_name} must be >= 0.")
        return normalized

    def _require_text(self, value: str, field_name: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValidationError(f"{field_name} is required.")
        return normalized

    def _require_datetime(self, value: object, field_name: str) -> datetime:
        if not isinstance(value, datetime):
            raise ValidationError(f"{field_name} phải là datetime hợp lệ.")
        return value
