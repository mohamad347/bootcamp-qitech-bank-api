from errors.base_error import QIException


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
