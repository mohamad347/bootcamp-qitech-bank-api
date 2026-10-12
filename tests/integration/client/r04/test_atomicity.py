"""Cen?rios de R04 organizados por comportamento."""

from .support import *


def test_account_creation_rolls_back_when_initial_event_fails(
    api_database_engine: Engine,
) -> None:
    client_key, email = _create_pending_individual()
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )

    with _reject_account_initial_event_for_client(api_database_engine, client_key):
        response = ClientRequisition.send(
            "POST",
            f"/client/{client_key}/account",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

    _assert_error_response(response, 500, INTERNAL_ERROR)
    assert _get_client_account_summary(api_database_engine, client_key) == {
        "status": "ACTIVE",
        "account_count": 0,
        "account_status": None,
        "account_event_count": 0,
        "client_event_count": 2,
    }
