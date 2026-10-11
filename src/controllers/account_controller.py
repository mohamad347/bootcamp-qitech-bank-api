
from uuid import UUID

from psycopg2.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError

from controllers.base_controller import BaseController
from dtos import AccountDTO
from errors import (
    AccountAlreadyExists,
    AccountNotFound,
    InvalidClientStatus,
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
                raise InvalidClientStatus(
                    current_status=client.status.enumerator,
                    required_status=ClientStatus.ACTIVE,
                )

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
        except IntegrityError as error:
            self.session.rollback()
            if (
                isinstance(error.orig, UniqueViolation)
                and error.orig.diag.constraint_name == "account_client_id_key"
            ):
                raise AccountAlreadyExists() from error
            raise
        except Exception:
            self.session.rollback()
            raise

    def get_by_key(self, account_key: str) -> dict:
        try:
            parsed_account_key = UUID(account_key)
        except (AttributeError, TypeError, ValueError):
            raise InvalidSchema("account_key must be a valid UUID") from None

        account_with_client_key = self.account_repository.get_by_key(
            parsed_account_key
        )
        if account_with_client_key is None:
            raise AccountNotFound(account_key)

        account, client_key = account_with_client_key
        return AccountDTO.obj_to_response(account, client_key)
