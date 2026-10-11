from errors.base_error import QIException


class ClientNotFound(QIException):
    code = "CLI0001"

    def __init__(self, client_key: str) -> None:
        super().__init__(
            title="Client not found",
            code=self.code,
            http_status=404,
            description=f"Client with key {client_key} was not found.",
            translation="O cliente informado não foi encontrado.",
        )


class DuplicateClientEmail(QIException):
    code = "CLI0003"

    def __init__(self, email: str) -> None:
        super().__init__(
            title="Email already registered",
            code=self.code,
            http_status=409,
            description=f"The email {email} is already registered.",
            translation="O e-mail informado já está cadastrado.",
        )


class DuplicateClientCPF(QIException):
    code = "CLI0004"

    def __init__(self) -> None:
        super().__init__(
            title="CPF already registered",
            code=self.code,
            http_status=409,
            description="The CPF is already registered.",
            translation="O CPF informado já está cadastrado.",
        )


class DuplicateClientCNPJ(QIException):
    code = "CLI0005"

    def __init__(self) -> None:
        super().__init__(
            title="CNPJ already registered",
            code=self.code,
            http_status=409,
            description="The CNPJ is already registered.",
            translation="O CNPJ informado já está cadastrado.",
        )


class InvalidClientDocument(QIException):
    code = "CLI0006"

    def __init__(self, document_type: str) -> None:
        super().__init__(
            title=f"Invalid {document_type}",
            code=self.code,
            http_status=400,
            description=f"The {document_type} is invalid.",
            translation=f"O {document_type} informado é inválido.",
        )


class UnsupportedClientTimezone(QIException):
    code = "CLI0008"

    def __init__(self) -> None:
        super().__init__(
            title="Unsupported timezone",
            code=self.code,
            http_status=400,
            description="The timezone is not supported for Brazilian clients.",
            translation=(
                "A timezone informada não é aceita para clientes brasileiros."
            ),
        )


class UnderageClient(QIException):
    code = "CLI0007"

    def __init__(self, age: int, minimum_age: int) -> None:
        super().__init__(
            title="Client is underage",
            code=self.code,
            http_status=422,
            description=f"The client is {age} years old; the minimum is {minimum_age}.",
            translation=f"É preciso ter pelo menos {minimum_age} anos.",
        )
