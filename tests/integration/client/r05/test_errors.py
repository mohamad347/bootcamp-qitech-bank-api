"""Testes da R05: cen?rios organizados por comportamento."""

from .support import *


def test_get_account_rejects_malformed_key() -> None:
    response = ClientRequisition.send(
        "GET", "/account/not-a-uuid", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )

    _assert_error_response(response, 400, INVALID_ACCOUNT_KEY_ERROR)


def test_get_account_rejects_unknown_key() -> None:
    account_key = str(uuid4())
    response = ClientRequisition.send(
        "GET", f"/account/{account_key}", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )

    _assert_error_response(
        response,
        404,
        {
            "title": "Account not found",
            "description": f"Account with key {account_key} was not found.",
            "translation": "A conta informada não foi encontrada.",
            "code": "ACC0001",
        },
    )


@pytest.mark.parametrize(
    ("account_key", "headers"),
    [
        (str(uuid4()), {}),
        (str(uuid4()), {"INTERNAL-TOKEN": "invalid-token"}),
        ("not-a-uuid", {"INTERNAL-TOKEN": "invalid-token"}),
    ],
)
def test_get_account_authentication_precedes_lookup_and_validation(
    account_key: str,
    headers: dict,
) -> None:
    response = ClientRequisition.send("GET", f"/account/{account_key}", headers=headers)

    _assert_error_response(response, 403, FORBIDDEN_ERROR)
