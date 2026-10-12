"""Cen?rios de R06 organizados por comportamento."""

from .support import *


@pytest.mark.parametrize("initial_status,target_status", [
    ("ACTIVE", "ACTIVE"),
    ("INACTIVE", "INACTIVE"),
])
def test_patch_account_rejects_same_status_without_side_effects(
    api_database_engine: Engine,
    initial_status: str,
    target_status: str,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    if initial_status == "INACTIVE":
        _prepare_inactive(account_key)
    before = _snapshot(api_database_engine, account_key)

    response = _patch(account_key, target_status)

    _assert_error(response, 409, "ACC0003")
    assert _snapshot(api_database_engine, account_key) == before


@pytest.mark.parametrize("target_status", ["ACTIVE", "INACTIVE", "CLOSED"])
def test_patch_account_closed_is_terminal(
    api_database_engine: Engine,
    target_status: str,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    assert _patch(account_key, "CLOSED").response_status == 200
    before = _snapshot(api_database_engine, account_key)

    response = _patch(account_key, target_status)

    _assert_error(response, 409, "ACC0003")
    assert _snapshot(api_database_engine, account_key) == before


@pytest.mark.parametrize("initial_status", ["ACTIVE", "INACTIVE"])
def test_patch_account_positive_balance_prevents_closure(
    api_database_engine: Engine,
    initial_status: str,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    if initial_status == "INACTIVE":
        _prepare_inactive(account_key)
    _set_balance(api_database_engine, account_key, 100)
    before = _snapshot(api_database_engine, account_key)

    response = _patch(account_key, "CLOSED")

    _assert_error(response, 409, "ACC0004")
    assert _snapshot(api_database_engine, account_key) == before


@pytest.mark.parametrize(
    ("account_status", "client_status", "target_status"),
    [("ACTIVE", "INACTIVE", "CLOSED"), ("INACTIVE", "ACTIVE", "CLOSED")],
)
def test_patch_account_rejects_incompatible_client_status(
    api_database_engine: Engine,
    account_status: str,
    client_status: str,
    target_status: str,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    if account_status == "INACTIVE":
        _prepare_inactive(account_key)
    _force_client_status(api_database_engine, account_key, client_status)
    before = _snapshot(api_database_engine, account_key)

    response = _patch(account_key, target_status)

    _assert_error(response, 409, "CLI0002")
    assert _snapshot(api_database_engine, account_key) == before
