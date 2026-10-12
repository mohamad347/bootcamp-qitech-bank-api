"""Cen?rios de R06 organizados por comportamento."""

from .support import *


@pytest.mark.parametrize("event_table", ["account_status_event", "client_status_event"])
def test_patch_account_rolls_back_when_event_insert_fails(
    api_database_engine: Engine,
    event_table: str,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    before = _snapshot(api_database_engine, account_key)

    with _reject_status_event_for_account(api_database_engine, account_key, event_table):
        response = _patch(account_key, "INACTIVE", "Falha controlada")

    _assert_error(response, 500, "QIT000500")
    assert _snapshot(api_database_engine, account_key) == before
