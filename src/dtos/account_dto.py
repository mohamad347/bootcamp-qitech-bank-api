from datetime import datetime, timezone
from uuid import UUID

from models import Account


class AccountDTO:
    """Representação pública do snapshot de ACCOUNT."""

    @staticmethod
    def obj_to_response(account: Account, client_key: UUID) -> dict:
        return {
            "account_key": str(account.account_key),
            "client_key": str(client_key),
            "status": account.status.enumerator,
            "balance_cents": account.balance_cents,
            "created_at": AccountDTO._as_utc_isoformat(account.created_at),
            "updated_at": AccountDTO._as_utc_isoformat(account.updated_at),
        }

    @staticmethod
    def _as_utc_isoformat(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
