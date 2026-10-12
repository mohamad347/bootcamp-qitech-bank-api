"""Cen?rios de R09 organizados por comportamento."""

from .support import *


def test_patch_client_rolls_back_when_status_event_insert_fails(
    api_database_engine: Engine,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")
    before = _snapshot(api_database_engine, client_key)

    with _reject_status_event_for_client(api_database_engine, client_key):
        response = _patch(client_key, "INACTIVE", "Falha controlada")

    _assert_error(response, 500, "QIT000500")
    assert _snapshot(api_database_engine, client_key) == before
