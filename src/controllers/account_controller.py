
from datetime import datetime, timezone
from uuid import UUID

from psycopg2.errors import UniqueViolation
from sqlalchemy.exc import IntegrityError

from controllers.base_controller import BaseController
from dtos import AccountDTO, AccountPatchDTO
from errors import (
    AccountBalancePreventsClosure,
    AccountAlreadyExists,
    AccountNotFound,
    InvalidAccountTransition,
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

    def update_status(self, account_key: str, payload: dict) -> dict:
        try:
            parsed_account_key = UUID(account_key)
        except (AttributeError, TypeError, ValueError):
            raise InvalidSchema("account_key must be a valid UUID") from None

        try:
            try:
                request_data = AccountPatchDTO.from_payload(payload)
            except ValueError as error:
                raise InvalidSchema(str(error)) from None

            client_id = self.account_repository.get_owner_id_by_key(
                parsed_account_key
            )
            if client_id is None:
                raise AccountNotFound(account_key)

            client = self.account_repository.get_client_by_id_for_update(client_id)
            account = self.account_repository.get_account_by_key_for_update(
                parsed_account_key,
                client_id,
            )
            if client is None or account is None:
                raise InternalError()

            account_status = self.account_repository.get_account_status_by_id(
                account.status_id
            )
            client_status = self.account_repository.get_client_status_by_id(
                client.status_id
            )
            if account_status is None or client_status is None:
                raise InternalError()

            current_account_status = account_status.enumerator
            current_client_status = client_status.enumerator
            target_status = request_data.status

            if (
                current_account_status == AccountStatus.CLOSED
                or current_account_status == target_status
            ):
                raise InvalidAccountTransition(
                    current_account_status,
                    target_status,
                )

            expected_client_status = {
                AccountStatus.ACTIVE: ClientStatus.ACTIVE,
                AccountStatus.INACTIVE: ClientStatus.INACTIVE,
            }.get(current_account_status)
            if expected_client_status is None:
                raise InternalError()
            if current_client_status != expected_client_status:
                raise InvalidClientStatus(
                    current_status=current_client_status,
                    required_status=expected_client_status,
                )

            allowed_targets = {
                AccountStatus.ACTIVE: {AccountStatus.INACTIVE, AccountStatus.CLOSED},
                AccountStatus.INACTIVE: {AccountStatus.ACTIVE, AccountStatus.CLOSED},
            }
            if target_status not in allowed_targets[current_account_status]:
                raise InvalidAccountTransition(
                    current_account_status,
                    target_status,
                )
            if target_status == AccountStatus.CLOSED and account.balance_cents != 0:
                raise AccountBalancePreventsClosure()

            target_account_status = self.account_repository.get_account_status(
                target_status
            )
            target_client_status_name = (
                ClientStatus.ACTIVE
                if target_status == AccountStatus.ACTIVE
                else ClientStatus.INACTIVE
            )
            target_client_status = self.account_repository.get_client_status(
                target_client_status_name
            )
            if target_account_status is None or target_client_status is None:
                raise InternalError()

            changed_at = datetime.now(timezone.utc)
            old_account_status_id = account.status_id
            account.status_id = target_account_status.id
            account.updated_at = changed_at
            self.account_repository.create_account_status_event(
                account_id=account.id,
                from_status_id=old_account_status_id,
                to_status_id=target_account_status.id,
                reason=request_data.reason,
                created_at=changed_at,
            )

            if current_client_status != target_client_status_name:
                old_client_status_id = client.status_id
                client.status_id = target_client_status.id
                client.updated_at = changed_at
                self.account_repository.create_client_status_event(
                    client_id=client.id,
                    from_status_id=old_client_status_id,
                    to_status_id=target_client_status.id,
                    reason=request_data.reason,
                    created_at=changed_at,
                )

            response = AccountPatchDTO.to_response(
                account.account_key,
                target_account_status.enumerator,
            )
            self.session.commit()
            return response
        except Exception:
            self.session.rollback()
            raise
