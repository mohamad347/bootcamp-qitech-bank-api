from errors.base_error import QIException


class InsufficientBalance(QIException):
    code = "TRX0001"

    def __init__(self) -> None:
        super().__init__(
            title="Insufficient balance",
            code=self.code,
            http_status=422,
            description=(
                "The source account balance is insufficient for the "
                "transaction amount and fee."
            ),
            translation=(
                "O saldo da conta de origem é insuficiente para o valor "
                "da transação e a tarifa."
            ),
        )


class SelfTransferNotAllowed(QIException):
    code = "TRX0002"

    def __init__(self) -> None:
        super().__init__(
            title="Self-transfer not allowed",
            code=self.code,
            http_status=409,
            description=(
                "The source and target accounts must be different."
            ),
            translation=(
                "As contas de origem e destino devem ser diferentes."
            ),
        )


class IdempotencyKeyConflict(QIException):
    code = "TRX0003"

    def __init__(self) -> None:
        super().__init__(
            title="Idempotency key conflict",
            code=self.code,
            http_status=409,
            description=(
                "The Idempotency-Key was already used for a different "
                "transaction."
            ),
            translation=(
                "A Idempotency-Key já foi utilizada em outra transação."
            ),
        )


class InvalidTransactionAmount(QIException):
    code = "TRX0004"

    def __init__(self) -> None:
        super().__init__(
            title="Invalid transaction amount",
            code=self.code,
            http_status=422,
            description=(
                "The transaction amount is outside the allowed financial "
                "range."
            ),
            translation=(
                "O valor da transação está fora do intervalo financeiro "
                "permitido."
            ),
        )


class InvalidTransactionDateRange(QIException):
    code = "TRX0005"

    def __init__(self) -> None:
        super().__init__(
            title="Invalid transaction date range",
            code=self.code,
            http_status=422,
            description="date_from must be less than or equal to date_to.",
            translation=(
                "date_from deve ser anterior ou igual a date_to."
            ),
        )
