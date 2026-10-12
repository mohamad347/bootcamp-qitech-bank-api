from datetime import datetime
from uuid import UUID

from sqlalchemy.orm import joinedload, selectinload

from database import Context
from models import FinancialTransaction, TransactionEntry


class TransactionRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def create_transaction(
        self,
        transaction_key: UUID,
        request_control_key: UUID,
        request_hash: str,
        transaction_type: str,
        created_at: datetime,
    ) -> FinancialTransaction:
        transaction = FinancialTransaction(
            transaction_key=transaction_key,
            request_control_key=request_control_key,
            request_hash=request_hash,
            transaction_type=transaction_type,
            created_at=created_at,
        )
        self.session.add(transaction)
        self.session.flush()
        return transaction

    def create_entry(
        self,
        transaction_id: int,
        account_id: int,
        direction: str,
        entry_type: str,
        amount_cents: int,
        balance_after_cents: int,
        created_at: datetime,
    ) -> TransactionEntry:
        entry = TransactionEntry(
            transaction_id=transaction_id,
            account_id=account_id,
            direction=direction,
            entry_type=entry_type,
            amount_cents=amount_cents,
            balance_after_cents=balance_after_cents,
            created_at=created_at,
        )
        self.session.add(entry)
        return entry

    def get_by_key_with_entries(
        self,
        transaction_key: UUID,
    ) -> FinancialTransaction:
        return (
            self.session.query(FinancialTransaction)
            .options(
                selectinload(FinancialTransaction.entries).joinedload(
                    TransactionEntry.account
                )
            )
            .filter(FinancialTransaction.transaction_key == transaction_key)
            .one()
        )

    def get_by_request_control_key_with_entries(
        self,
        request_control_key: UUID,
    ) -> FinancialTransaction | None:
        return (
            self.session.query(FinancialTransaction)
            .options(
                selectinload(FinancialTransaction.entries).joinedload(
                    TransactionEntry.account
                )
            )
            .filter(
                FinancialTransaction.request_control_key
                == request_control_key
            )
            .one_or_none()
        )
