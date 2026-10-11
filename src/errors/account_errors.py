
from errors.base_error import QIException


class AccountNotFound(QIException):
    code = "ACC0001"

    def __init__(self, account_key: str) -> None:
        super().__init__(
            title="Account not found",
            code=self.code,
            http_status=404,
            description=f"Account with key {account_key} was not found.",
            translation="A conta informada não foi encontrada.",
        )


class AccountAlreadyExists(QIException):
    code = "ACC0002"

    def __init__(self) -> None:
        super().__init__(
            title="Client already has an account",
            code=self.code,
            http_status=409,
            description="The client already has an account.",
            translation="O cliente já possui uma conta.",
        )
