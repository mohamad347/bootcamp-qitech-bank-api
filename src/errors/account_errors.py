
from errors.base_error import QIException


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
