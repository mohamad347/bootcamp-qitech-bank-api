"""Testes da R05: cen?rios organizados por comportamento."""

from .support import *


@pytest.mark.parametrize("client_type", ["INDIVIDUAL", "COMPANY"])
def test_get_account_returns_persisted_snapshot_for_active_owner(
    api_database_engine: Engine,
    client_type: str,
) -> None:
    _, account_key = _create_active_account(api_database_engine, client_type)
    persisted = _get_persisted_account(api_database_engine, account_key)

    response = ClientRequisition.send(
        "GET", f"/account/{account_key}", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )

    _assert_account_snapshot_response(response, persisted)


@pytest.mark.parametrize("target_status", ["INACTIVE", "CLOSED"])
def test_get_account_returns_all_non_active_statuses(
    api_database_engine: Engine,
    target_status: str,
) -> None:
    _, account_key = _create_active_account(api_database_engine, "INDIVIDUAL")
    _transition_account_status(api_database_engine, account_key, target_status)
    persisted = _get_persisted_account(api_database_engine, account_key)

    response = ClientRequisition.send(
        "GET", f"/account/{account_key}", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )

    _assert_account_snapshot_response(response, persisted)


def test_get_account_returns_current_persisted_balance_and_timestamps(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine, "INDIVIDUAL")
    _set_account_balance(api_database_engine, account_key, 125000)
    persisted = _get_persisted_account(api_database_engine, account_key)

    response = ClientRequisition.send(
        "GET", f"/account/{account_key}", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )

    _assert_account_snapshot_response(response, persisted)
    assert response.response_json["balance_cents"] == 125000
