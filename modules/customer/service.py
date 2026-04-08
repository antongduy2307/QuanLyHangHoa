from __future__ import annotations

from collections.abc import Sequence
from contextlib import nullcontext
from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from core.exceptions import ValidationError
from modules.customer.dto import CustomerDTO
from modules.customer.mappers import to_dto
from modules.customer.models import Customer, CustomerBalanceLedger
from modules.customer.repository import CustomerRepository


class CustomerService:
    def __init__(self, repository: CustomerRepository) -> None:
        self._repository = repository

    def use_session(self, session: Session) -> None:
        self._repository.use_session(session)

    def list_customers(self) -> Sequence[CustomerDTO]:
        return [to_dto(customer) for customer in self._repository.list_customers()]

    def get_customer(self, customer_id: int) -> Customer:
        return self._repository.get_customer(customer_id)

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
        normalized_initial_balance = self._to_decimal(initial_balance)
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = Customer(
                customer_name=normalized_name,
                phone=normalized_phone,
                address=normalized_address,
                current_balance=Decimal("0"),
                total_sales=Decimal("0"),
                is_walk_in=False,
            )
            session.add(customer)
            session.flush()
            if normalized_initial_balance != Decimal("0"):
                self._append_balance_ledger(
                    customer,
                    amount_delta=normalized_initial_balance,
                    ref_type="OPENING_BALANCE",
                    ref_id=customer.id,
                    event_type="OPENING_BALANCE",
                    note=note or "Opening balance",
                )
            session.flush()
            return customer

    def update_customer(
        self,
        customer_id: int,
        *,
        customer_name: str,
        phone: str | None = None,
        address: str | None = None,
        target_balance: Decimal | int | str | None = None,
        balance_note: str | None = None,
    ) -> Customer:
        session = self._repository.session
        normalized_name = self._require_text(customer_name, "customer_name")
        normalized_phone = self._normalize_optional_text(phone)
        normalized_address = self._normalize_optional_text(address)
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = self._repository.get_customer(customer_id)
            customer.customer_name = normalized_name
            customer.phone = normalized_phone
            customer.address = normalized_address

            if target_balance is not None:
                normalized_target_balance = self._to_decimal(target_balance)
                delta = normalized_target_balance - customer.current_balance
                if delta != Decimal("0"):
                    self._append_balance_ledger(
                        customer,
                        amount_delta=delta,
                        ref_type="BALANCE_ADJUSTMENT",
                        ref_id=self._generate_ref_id(),
                        event_type="BALANCE_ADJUSTMENT",
                        note=balance_note or "Manual balance adjustment",
                    )
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
            customer.current_balance = customer.current_balance - net_delta
            for ledger in ledgers:
                session.delete(ledger)
            session.flush()
            return net_delta

    def adjust_balance(
        self,
        customer_id: int,
        amount_delta: Decimal | int | str,
        ref_type: str,
        ref_id: int,
        note: str | None = None,
        event_type: str = "ADJUSTMENT",
    ) -> CustomerBalanceLedger:
        session = self._repository.session
        normalized_delta = self._require_non_zero_decimal(amount_delta, "amount_delta")
        normalized_ref_type = self._require_text(ref_type, "ref_type")
        normalized_event_type = self._require_text(event_type, "event_type")
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
            )
            session.flush()
            return ledger

    def pay_debt(self, customer_id: int, amount: Decimal | int | str, note: str | None = None) -> CustomerBalanceLedger:
        normalized_amount = self._require_positive_decimal(amount, "amount")
        ref_id = self._generate_ref_id()
        return self.adjust_balance(
            customer_id,
            amount_delta=normalized_amount * Decimal("-1"),
            ref_type="DEBT_PAYMENT",
            ref_id=ref_id,
            note=note,
            event_type="DEBT_PAYMENT",
        )

    def update_debt_payment(self, ledger_id: int, new_amount: Decimal | int | str, note: str | None = None) -> CustomerBalanceLedger:
        session = self._repository.session
        normalized_amount = self._require_positive_decimal(new_amount, "new_amount")
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            original_ledger = self._repository.get_ledger(ledger_id)
            if original_ledger.event_type != "DEBT_PAYMENT" or original_ledger.ref_type != "DEBT_PAYMENT":
                raise ValidationError("Giao dịch được chọn không phải là giao dịch trả nợ hợp lệ.")
            customer = self._repository.get_customer(original_ledger.customer_id)

            rollback_amount = original_ledger.amount_delta * Decimal("-1")
            self._append_balance_ledger(
                customer,
                amount_delta=rollback_amount,
                ref_type="DEBT_PAYMENT",
                ref_id=original_ledger.ref_id,
                event_type="DEBT_PAYMENT_EDIT_ROLLBACK",
                note=f"Rollback debt payment {original_ledger.ref_id}",
            )
            replacement = self._append_balance_ledger(
                customer,
                amount_delta=normalized_amount * Decimal("-1"),
                ref_type="DEBT_PAYMENT",
                ref_id=original_ledger.ref_id,
                event_type="DEBT_PAYMENT",
                note=note,
                created_at=original_ledger.created_at,
            )
            session.flush()
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
            return rollback_ledger

    def _append_balance_ledger(
        self,
        customer: Customer,
        *,
        amount_delta: Decimal,
        ref_type: str,
        ref_id: int,
        event_type: str,
        note: str | None,
        created_at: datetime | None = None,
    ) -> CustomerBalanceLedger:
        balance_after = customer.current_balance + amount_delta
        customer.current_balance = balance_after
        ledger = CustomerBalanceLedger(
            customer_id=customer.id,
            event_type=event_type,
            ref_type=ref_type,
            ref_id=int(ref_id),
            amount_delta=amount_delta,
            balance_after=balance_after,
            note=note,
        )
        if created_at is not None:
            ledger.created_at = created_at
        self._repository.session.add(ledger)
        return ledger

    @staticmethod
    def _generate_ref_id() -> int:
        return int(datetime.now().timestamp() * 1_000_000)

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
