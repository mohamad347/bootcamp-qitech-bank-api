from uuid import UUID

from controllers.base_controller import BaseController
from errors import (
    AccountAlreadyExists,
    ClientNotActive,
    ClientNotFound,
    InternalError,
    InvalidSchema,
)
from models import AccountStatus, ClientStatus
from repositories import AccountRepository


class AccountController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.account_repository = AccountRepository(self.context)

    def create_for_client(self, client_key: str) -> dict:
        try:
            parsed_client_key = UUID(client_key)
        except (AttributeError, TypeError, ValueError):
            raise InvalidSchema("client_key must be a valid UUID") from None

        try:
            client = self.account_repository.get_client_by_key_for_update(
                parsed_client_key
            )
            if client is None:
                raise ClientNotFound(client_key)

            if client.status.enumerator != ClientStatus.ACTIVE:
                raise ClientNotActive()

            if self.account_repository.get_by_client_id(client.id) is not None:
                raise AccountAlreadyExists()

            active_status = self.account_repository.get_account_status(
                AccountStatus.ACTIVE
            )
            if active_status is None:
                raise InternalError()

            account = self.account_repository.create_account(
                client_id=client.id,
                status=active_status,
            )
            self.account_repository.create_initial_status_event(
                account_id=account.id,
                status=active_status,
            )

            response = {
                "account_key": str(account.account_key),
                "status": active_status.enumerator,
                "balance_cents": account.balance_cents,
            }
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            raise
