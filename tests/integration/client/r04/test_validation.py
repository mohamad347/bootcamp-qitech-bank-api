"""Cen?rios de R04 organizados por comportamento."""

from .support import *


def test_create_account_rejects_malformed_client_key() -> None:
    response = ClientRequisition.send(
        "POST",
        "/client/not-a-uuid/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_error_response(response, 400, INVALID_CLIENT_KEY_ERROR)


def test_create_account_rejects_unknown_client_key() -> None:
    client_key = str(uuid4())
    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_error_response(response, 404, _expected_client_not_found_error(client_key))


@pytest.mark.parametrize(
    ("headers", "case"),
    [
        (None, "missing"),
        ({"INTERNAL-TOKEN": "invalid-token"}, "invalid"),
    ],
)
def test_create_account_rejects_unauthenticated_requests_without_writes(
    api_database_engine: Engine,
    headers: dict[str, str] | None,
    case: str,
) -> None:
    client_key, email = _create_pending_individual()
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )

    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers=headers,
    )

    _assert_error_response(response, 403, FORBIDDEN_ERROR)
    assert _get_client_account_summary(api_database_engine, client_key) == {
        "status": "ACTIVE",
        "account_count": 0,
        "account_status": None,
        "account_event_count": 0,
        "client_event_count": 2,
    }


@pytest.mark.parametrize("client_key", ["not-a-uuid", str(uuid4())])
def test_authentication_precedes_client_key_validation(client_key: str) -> None:
    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": "invalid-token"},
    )

    _assert_error_response(response, 403, FORBIDDEN_ERROR)
