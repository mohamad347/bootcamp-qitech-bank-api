
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


class InvalidAccountTransition(QIException):
    code = "ACC0003"

    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            title="Invalid account status transition",
            code=self.code,
            http_status=409,
            description=(
                f"Account cannot transition from {current_status} to {target_status}."
            ),
            translation=(
                f"A conta não pode mudar de {current_status} para {target_status}."
            ),
        )


class AccountBalancePreventsClosure(QIException):
    code = "ACC0004"

    def __init__(self) -> None:
        super().__init__(
            title="Account balance prevents closure",
            code=self.code,
            http_status=409,
            description="The account balance must be zero before closure.",
            translation="O saldo da conta deve estar zerado antes do encerramento.",
        )
