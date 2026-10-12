"""Cen?rios de R04 organizados por comportamento."""

from .support import *


def test_concurrent_account_openings_create_exactly_one_account(
    api_database_engine: Engine,
) -> None:
    client_key, email = _create_pending_individual()
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )
    start_requests = Barrier(3)

    def create_account_concurrently():
        start_requests.wait(timeout=5)
        return ClientRequisition.send(
            "POST",
            f"/client/{client_key}/account",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

    with api_database_engine.connect() as lock_connection:
        transaction = lock_connection.begin()
        locked_client_id = lock_connection.execute(
            text(
                """
                SELECT id
                FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                FOR UPDATE
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        assert locked_client_id

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(create_account_concurrently)
                for _ in range(2)
            ]
            try:
                start_requests.wait(timeout=5)
                _wait_for_client_lock_wait(lock_connection, client_key)
            finally:
                # Esta transação é apenas o gate do teste: rollback libera
                # sempre o FOR UPDATE antes de aguardar as threads.
                if transaction.is_active:
                    transaction.rollback()

            responses = [future.result(timeout=10) for future in futures]

    successful = [response for response in responses if response.response_status == 201]
    conflicts = [response for response in responses if response.response_status == 409]
    assert len(successful) == 1
    assert len(conflicts) == 1
    _assert_created_account_response(successful[0], client_key)
    _assert_error_response(conflicts[0], 409, ACCOUNT_ALREADY_EXISTS_ERROR)
    assert _get_client_account_summary(api_database_engine, client_key) == {
        "status": "ACTIVE",
        "account_count": 1,
        "account_status": "ACTIVE",
        "account_event_count": 1,
        "client_event_count": 2,
    }
