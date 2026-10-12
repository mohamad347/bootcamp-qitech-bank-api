from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from errors.base_error import (
    QIException,
    InternalError,
    InvalidParameter,
    InvalidSchema,
    MethodNotAllowed,
    NotFoundResource,
)
def qi_exception_to_response(exception: QIException) -> JSONResponse:
    """Traduz um erro nosso para a resposta JSON que o cliente recebe.

    Este é o único lugar do projeto que sabe como um erro vira HTTP.
    Trocar de framework significa reescrever esta função — e mais nada.
    """
    body = {
        "title": exception.title,
        "description": exception.description,
        "translation": exception.translation,
        "code": exception.code,
    }
    return JSONResponse(status_code=exception.http_status, content=body)


def describe_validation_error(error: dict) -> str:
    location = []
    for part in error.get("loc", []):
        if part not in ("body", "query"):
            location.append(str(part))

    message = error.get("msg", "invalid value")

    if location:
        return f"{message} in {'.'.join(location)}"

    return message


def register_error_handlers(application: FastAPI) -> None:
    """Ensina a aplicação a responder cada tipo de erro."""

    @application.exception_handler(QIException)
    def handle_qi_exception(request: Request, exception: QIException) -> JSONResponse:
        request.state.error_code = exception.code
        return qi_exception_to_response(exception)

    @application.exception_handler(StarletteHTTPException)
    def handle_http_exception(request: Request, exception: StarletteHTTPException) -> JSONResponse:
        if exception.status_code == 404:
            request.state.error_code = NotFoundResource.code
            return qi_exception_to_response(NotFoundResource())

        if exception.status_code == 405:
            request.state.error_code = MethodNotAllowed.code
            return qi_exception_to_response(MethodNotAllowed())

        request.state.error_code = InternalError.code
        return qi_exception_to_response(InternalError())

    @application.exception_handler(RequestValidationError)
    def handle_validation_error(request: Request, exception: RequestValidationError) -> JSONResponse:
        errors = exception.errors()

        if errors:
            first_error = errors[0]
        else:
            first_error = {}

        description = describe_validation_error(first_error)
        origin = first_error.get("loc", [""])[0]

        # Este ramo NAO e alcancado hoje, e vale saber por que — e a
        # unica pista de que existem duas validacoes neste projeto, nao
        # uma.
        #
        # Quem julga a query string aqui e o JSON Schema, antes do
        # FastAPI (veja utils/schema_handler.py). Um ?page=-3 morre la,
        # com 400 QIT000001 — nunca chega a virar RequestValidationError.
        # E os parametros de endereco sao todos `str`, que nao tem como
        # falhar validacao.
        #
        # O ramo fica de pe para o dia em que alguma rota declarar um
        # parametro tipado (page: int) e passar a depender do FastAPI
        # para isso. O QIT000010 que o cliente ve hoje vem de outro
        # lugar: do controller, quando birthdate_from > birthdate_to.
        if origin in ("query", "path"):
            error = InvalidParameter(description)
            request.state.error_code = error.code
            return qi_exception_to_response(error)

        error = InvalidSchema(description)
        request.state.error_code = error.code
        return qi_exception_to_response(error)

    @application.exception_handler(Exception)
    def handle_unexpected_error(request: Request, exception: Exception) -> JSONResponse:
        request.state.error_code = InternalError.code
        return qi_exception_to_response(InternalError())
