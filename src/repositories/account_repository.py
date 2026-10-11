from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy.orm import lazyload

from database import Context
from models import Account, AccountStatus, AccountStatusEvent, Client


class AccountRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def get_client_by_key_for_update(self, client_key: UUID) -> Client | None:
        return (
            self.session.query(Client)
            .options(lazyload(Client.status))
            .filter(Client.client_key == client_key)
            .populate_existing()
            .with_for_update(of=Client)
            .one_or_none()
        )

    def get_account_status(self, enumerator: str) -> AccountStatus | None:
        return (
            self.session.query(AccountStatus)
            .filter(AccountStatus.enumerator == enumerator)
            .one_or_none()
        )

    def get_by_client_id(self, client_id: int) -> Account | None:
        return (
            self.session.query(Account)
            .filter(Account.client_id == client_id)
            .one_or_none()
        )

    def create_account(self, client_id: int, status: AccountStatus) -> Account:
        now = datetime.now(timezone.utc)
        account = Account(
            account_key=uuid4(),
            client_id=client_id,
            status_id=status.id,
            balance_cents=0,
            created_at=now,
            updated_at=now,
        )
        self.session.add(account)
        self.session.flush()
        return account

    def create_initial_status_event(
        self,
        account_id: int,
        status: AccountStatus,
    ) -> AccountStatusEvent:
        event = AccountStatusEvent(
            account_id=account_id,
            from_status_id=None,
            to_status_id=status.id,
            actor_type=AccountStatusEvent.SYSTEM,
            reason=None,
            created_at=datetime.now(timezone.utc),
        )
        self.session.add(event)
        return event
