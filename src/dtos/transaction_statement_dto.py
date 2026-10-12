from datetime import datetime, timezone
from uuid import UUID

from models import FinancialTransaction, TransactionEntry


class TransactionStatementDTO:
    """Transforma uma entry financeira persistida em item de extrato."""

    @staticmethod
    def obj_to_response(entry: TransactionEntry) -> dict:
        transaction = entry.transaction
        counterparty_account_key = (
            TransactionStatementDTO._counterparty_account_key(entry)
        )
        return {
            "transaction_key": str(transaction.transaction_key),
            "transaction_type": transaction.transaction_type,
            "entry_type": entry.entry_type,
            "direction": entry.direction,
            "amount_cents": entry.amount_cents,
            "balance_after_cents": entry.balance_after_cents,
            "counterparty_account_key": (
                str(counterparty_account_key)
                if counterparty_account_key is not None
                else None
            ),
            "created_at": TransactionStatementDTO._as_utc_isoformat(
                transaction.created_at
            ),
        }

    @staticmethod
    def _counterparty_account_key(entry: TransactionEntry) -> UUID | None:
        transaction = entry.transaction
        if (
            transaction.transaction_type != FinancialTransaction.TRANSFER
            or entry.entry_type != TransactionEntry.PRINCIPAL
        ):
            return None

        counterparty_direction = (
            TransactionEntry.CREDIT
            if entry.direction == TransactionEntry.DEBIT
            else TransactionEntry.DEBIT
        )
        counterparty_entry = next(
            sibling
            for sibling in transaction.entries
            if sibling.entry_type == TransactionEntry.PRINCIPAL
            and sibling.direction == counterparty_direction
        )
        return counterparty_entry.account.account_key

    @staticmethod
    def _as_utc_isoformat(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
