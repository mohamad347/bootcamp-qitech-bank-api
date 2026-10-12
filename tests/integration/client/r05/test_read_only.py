"""Testes da R05: cen?rios organizados por comportamento."""

from .support import *


def test_get_account_is_idempotent_and_does_not_mutate_persistence(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine, "INDIVIDUAL")
    before = _get_persisted_account(api_database_engine, account_key)

    first_response = ClientRequisition.send(
        "GET", f"/account/{account_key}", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )
    second_response = ClientRequisition.send(
        "GET", f"/account/{account_key}", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )

    after = _get_persisted_account(api_database_engine, account_key)
    _assert_account_snapshot_response(first_response, before)
    assert second_response.response_json == first_response.response_json
    assert after == before
    assert before["account_event_count"] == 1
    assert before["client_event_count"] == 2
    assert before["entry_count"] == 0
    assert before["transaction_count"] == 0
