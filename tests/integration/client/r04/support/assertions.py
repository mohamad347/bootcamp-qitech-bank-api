"""Helpers coesos e locais da rota R04."""

from .base import *


def _assert_created_account_response(response, client_key: str) -> None:
    assert response.response_status == 201
    assert response.response.headers["content-type"].startswith("application/json")

    response_body = response.response_json
    assert isinstance(response_body, dict)
    assert set(response_body) == ACCOUNT_RESPONSE_FIELDS
    assert isinstance(UUID(response_body["account_key"]), UUID)
    assert response_body["account_key"] != client_key
    assert response_body["status"] == "ACTIVE"
    assert type(response_body["balance_cents"]) is int
    assert response_body["balance_cents"] == 0


def _expected_client_not_found_error(client_key: str) -> dict[str, str]:
    return {
        "title": "Client not found",
        "description": f"Client with key {client_key} was not found.",
        "translation": "O cliente informado não foi encontrado.",
        "code": "CLI0001",
    }


def _expected_invalid_client_status_error(current_status: str) -> dict[str, str]:
    return {
        "title": "Client status conflict",
        "description": (
            f"Client with status {current_status} cannot perform an operation "
            "that requires status ACTIVE."
        ),
        "translation": (
            f"O cliente com status {current_status} não pode executar uma "
            "operação que exige o status ACTIVE."
        ),
        "code": "CLI0002",
    }


def _assert_error_response(
    response,
    status_code: int,
    expected_body: dict[str, str],
) -> None:
    assert response.response_status == status_code
    assert response.response_json == expected_body

__all__ = [name for name in globals() if not name.startswith("__")]
