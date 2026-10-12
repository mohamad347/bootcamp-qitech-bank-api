from datetime import datetime, timezone

from models import FinancialTransaction, TransactionEntry


class TransactionDTO:
    """Transforma o estado financeiro persistido na resposta pública."""

    @staticmethod
    def obj_to_response(transaction: FinancialTransaction) -> dict:
        principal_entry = next(
            entry
            for entry in transaction.entries
            if entry.direction == TransactionEntry.CREDIT
            and entry.entry_type == TransactionEntry.PRINCIPAL
        )
        fee_cents = sum(
            entry.amount_cents
            for entry in transaction.entries
            if entry.entry_type == TransactionEntry.FEE
        )

        return {
            "transaction_key": str(transaction.transaction_key),
            "transaction_type": transaction.transaction_type,
            "account_key": str(principal_entry.account.account_key),
            "counterparty_account_key": None,
            "amount_cents": principal_entry.amount_cents,
            "fee_cents": fee_cents,
            "created_at": TransactionDTO._as_utc_isoformat(
                transaction.created_at
            ),
        }

    @staticmethod
    def _as_utc_isoformat(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
