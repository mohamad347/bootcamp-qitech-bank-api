from datetime import datetime, timezone

from models import FinancialTransaction, TransactionEntry


class TransactionDTO:
    """Transforma o estado financeiro persistido na resposta pública."""

    @staticmethod
    def obj_to_response(transaction: FinancialTransaction) -> dict:
        if transaction.transaction_type == FinancialTransaction.TRANSFER:
            source_entry = next(
                entry
                for entry in transaction.entries
                if entry.direction == TransactionEntry.DEBIT
                and entry.entry_type == TransactionEntry.PRINCIPAL
            )
            target_entry = next(
                entry
                for entry in transaction.entries
                if entry.direction == TransactionEntry.CREDIT
                and entry.entry_type == TransactionEntry.PRINCIPAL
            )
            fee_entry = next(
                entry
                for entry in transaction.entries
                if entry.direction == TransactionEntry.DEBIT
                and entry.entry_type == TransactionEntry.FEE
            )
            account_key = source_entry.account.account_key
            counterparty_account_key = target_entry.account.account_key
            amount_cents = source_entry.amount_cents
            fee_cents = fee_entry.amount_cents
        else:
            principal_entry = next(
                entry
                for entry in transaction.entries
                if entry.direction == TransactionEntry.CREDIT
                and entry.entry_type == TransactionEntry.PRINCIPAL
            )
            account_key = principal_entry.account.account_key
            counterparty_account_key = None
            amount_cents = principal_entry.amount_cents
            fee_cents = 0

        return {
            "transaction_key": str(transaction.transaction_key),
            "transaction_type": transaction.transaction_type,
            "account_key": str(account_key),
            "counterparty_account_key": (
                str(counterparty_account_key)
                if counterparty_account_key is not None
                else None
            ),
            "amount_cents": amount_cents,
            "fee_cents": fee_cents,
            "created_at": TransactionDTO._as_utc_isoformat(
                transaction.created_at
            ),
        }

    @staticmethod
    def _as_utc_isoformat(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
