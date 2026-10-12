"""Cen?rios de R06 organizados por comportamento."""

from .support import *


def test_concurrent_same_transition_creates_one_pair_of_events(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    before = _snapshot(api_database_engine, account_key)
    barrier = Barrier(3)

    def patch_concurrently():
        barrier.wait(timeout=5)
        return _patch(account_key, "INACTIVE", "Concorrência R06")

    with api_database_engine.connect() as lock_connection:
        transaction = lock_connection.begin()
        lock_connection.execute(
            text(
                """
                SELECT client.id FROM client
                JOIN account ON account.client_id = client.id
                WHERE account.account_key = CAST(:account_key AS uuid)
                FOR UPDATE OF client
                """
            ),
            {"account_key": account_key},
        ).scalar_one()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(patch_concurrently) for _ in range(2)]
            try:
                barrier.wait(timeout=5)
                _wait_for_blocked_request(lock_connection, "CLIENT")
            finally:
                if transaction.is_active:
                    transaction.rollback()
            responses = [future.result(timeout=10) for future in futures]

    assert sorted(response.response_status for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.response_status == 409)
    _assert_error(conflict, 409, "ACC0003")
    after = _snapshot(api_database_engine, account_key)
    assert (after["account_status"], after["client_status"]) == ("INACTIVE", "INACTIVE")
    assert after["account_event_count"] == before["account_event_count"] + 1
    assert after["client_event_count"] == before["client_event_count"] + 1


def test_patch_locks_client_before_account_and_revalidates_balance(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    with api_database_engine.connect() as account_lock_connection:
        transaction = account_lock_connection.begin()
        locked = account_lock_connection.execute(
            text(
                """
                SELECT account.id, account.client_id FROM account
                WHERE account.account_key = CAST(:account_key AS uuid)
                FOR UPDATE
                """
            ),
            {"account_key": account_key},
        ).mappings().one()
        account_lock_connection.execute(
            text("UPDATE account SET balance_cents = 100 WHERE id = :account_id"),
            {"account_id": locked["id"]},
        )

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_patch, account_key, "CLOSED", "Fechamento concorrente")
            try:
                _wait_for_blocked_request(account_lock_connection, "ACCOUNT")
                with api_database_engine.connect() as client_probe:
                    probe_transaction = client_probe.begin()
                    try:
                        with pytest.raises(OperationalError) as lock_error:
                            client_probe.execute(
                                text("SELECT id FROM client WHERE id = :client_id FOR UPDATE NOWAIT"),
                                {"client_id": locked["client_id"]},
                            )
                        assert isinstance(lock_error.value.orig, LockNotAvailable)
                    finally:
                        probe_transaction.rollback()
            finally:
                if transaction.is_active:
                    transaction.commit()
            response = future.result(timeout=10)

    _assert_error(response, 409, "ACC0004")
    after = _snapshot(api_database_engine, account_key)
    assert after["balance_cents"] == 100
    assert (after["account_status"], after["client_status"]) == ("ACTIVE", "ACTIVE")
