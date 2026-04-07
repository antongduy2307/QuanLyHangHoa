from __future__ import annotations

from collections.abc import Sequence
from contextlib import nullcontext
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
            balance_after = customer.current_balance + normalized_delta
            customer.current_balance = balance_after

            ledger = CustomerBalanceLedger(
                customer_id=customer.id,
                event_type=normalized_event_type,
                ref_type=normalized_ref_type,
                ref_id=int(ref_id),
                amount_delta=normalized_delta,
                balance_after=balance_after,
                note=note,
            )
            session.add(ledger)
            session.flush()
            return ledger

    def increase_sales(self, customer_id: int, amount: Decimal | int | str) -> Customer:
        session = self._repository.session
        normalized_amount = self._require_non_negative_decimal(amount, "amount")
        transaction_context = nullcontext() if session.in_transaction() else session.begin()

        with transaction_context:
            customer = self._repository.get_customer(customer_id)
            customer.total_sales = customer.total_sales + normalized_amount
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
            balance_after = customer.current_balance + amount_to_reverse
            customer.current_balance = balance_after

            rollback_ledger = CustomerBalanceLedger(
                customer_id=customer.id,
                event_type="ROLLBACK",
                ref_type=normalized_ref_type,
                ref_id=normalized_ref_id,
                amount_delta=amount_to_reverse,
                balance_after=balance_after,
                note=f"Rollback for {normalized_ref_type}:{normalized_ref_id}",
            )
            session.add(rollback_ledger)
            session.flush()
            return rollback_ledger

    @staticmethod
    def _to_decimal(value: Decimal | int | str) -> Decimal:
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    def _require_non_zero_decimal(self, value: Decimal | int | str, field_name: str) -> Decimal:
        normalized = self._to_decimal(value)
        if normalized == Decimal("0"):
            raise ValidationError(f"{field_name} must not be 0.")
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
