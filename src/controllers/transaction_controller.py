from datetime import datetime, timezone
from uuid import UUID, uuid4

from controllers.base_controller import BaseController
from controllers.transaction_hash import build_deposit_request_hash
from dtos import TransactionDTO
from errors import (
    AccountNotActive,
    AccountNotFound,
    IdempotencyKeyConflict,
    InvalidSchema,
    InvalidTransactionAmount,
)
from models import AccountStatus, FinancialTransaction, TransactionEntry
from repositories import AccountRepository, TransactionRepository


BIGINT_MAX = 9_223_372_036_854_775_807


class TransactionController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.account_repository = AccountRepository(self.context)
        self.transaction_repository = TransactionRepository(self.context)

    def create(
        self,
        account_key: str,
        idempotency_key: str | None,
        transaction_data: dict,
    ) -> dict:
        try:
            parsed_account_key = UUID(account_key)
        except (AttributeError, TypeError, ValueError):
            raise InvalidSchema("account_key must be a valid UUID") from None

        try:
            parsed_idempotency_key = UUID(idempotency_key)
        except (AttributeError, TypeError, ValueError):
            raise InvalidSchema("Idempotency-Key must be a valid UUID") from None

        if transaction_data["transaction_type"] != "DEPOSIT":
            raise RuntimeError("TRANSFER is not implemented yet")

        amount_cents = transaction_data["amount_cents"]
        request_hash = build_deposit_request_hash(
            parsed_account_key,
            amount_cents,
        )

        try:
            existing_transaction = (
                self.transaction_repository.get_by_request_control_key_with_entries(
                    parsed_idempotency_key
                )
            )
            if existing_transaction is not None:
                if existing_transaction.request_hash == request_hash:
                    return TransactionDTO.obj_to_response(existing_transaction)
                raise IdempotencyKeyConflict()

            if amount_cents < 1 or amount_cents > BIGINT_MAX:
                raise InvalidTransactionAmount()

            account = self.account_repository.get_by_key_for_update(
                parsed_account_key
            )
            if account is None:
                raise AccountNotFound(account_key)
            if account.status.enumerator != AccountStatus.ACTIVE:
                raise AccountNotActive(account.status.enumerator)
            if account.balance_cents > BIGINT_MAX - amount_cents:
                raise InvalidTransactionAmount()

            transaction_created_at = datetime.now(timezone.utc)
            transaction_key = uuid4()
            transaction = self.transaction_repository.create_transaction(
                transaction_key=transaction_key,
                request_control_key=parsed_idempotency_key,
                request_hash=request_hash,
                transaction_type=FinancialTransaction.DEPOSIT,
                created_at=transaction_created_at,
            )
            balance_after_cents = account.balance_cents + amount_cents
            self.transaction_repository.create_entry(
                transaction_id=transaction.id,
                account_id=account.id,
                direction=TransactionEntry.CREDIT,
                entry_type=TransactionEntry.PRINCIPAL,
                amount_cents=amount_cents,
                balance_after_cents=balance_after_cents,
                created_at=transaction_created_at,
            )
            self.account_repository.update_balance(
                account=account,
                balance_cents=balance_after_cents,
                updated_at=transaction_created_at,
            )

            self.session.commit()
            persisted_transaction = (
                self.transaction_repository.get_by_key_with_entries(
                    transaction_key
                )
            )
            return TransactionDTO.obj_to_response(persisted_transaction)
        except Exception:
            self.session.rollback()
            raise
