"""Cen?rios de R09 organizados por comportamento."""

from .support import *


def test_concurrent_r09_requests_create_exactly_one_transition(
    api_database_engine: Engine,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")
    before = _snapshot(api_database_engine, client_key)
    barrier = Barrier(3)

    def patch_concurrently():
        barrier.wait(timeout=5)
        return _patch(client_key, "INACTIVE", "Concorrência R09")

    with api_database_engine.connect() as lock_connection:
        transaction = lock_connection.begin()
        lock_connection.execute(
            text(
                """
                SELECT id FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                FOR UPDATE
                """
            ),
            {"client_key": client_key},
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
    _assert_error(conflict, 409, "CLI0002")
    after = _snapshot(api_database_engine, client_key)
    assert after["client_status"] == "INACTIVE"
    assert after["client_event_count"] == before["client_event_count"] + 1


def test_concurrent_reanalysis_from_rejected_creates_one_pending_transition(
    api_database_engine: Engine,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "REJECTED")
    before = _snapshot(api_database_engine, client_key)
    barrier = Barrier(3)

    def request_reanalysis():
        barrier.wait(timeout=5)
        return _patch(client_key, "PENDING", "Reanálise concorrente")

    with api_database_engine.connect() as lock_connection:
        transaction = lock_connection.begin()
        lock_connection.execute(
            text(
                """
                SELECT id FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                FOR UPDATE
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(request_reanalysis) for _ in range(2)]
            try:
                barrier.wait(timeout=5)
                _wait_for_blocked_request(lock_connection, "CLIENT/REANALYSIS")
            finally:
                if transaction.is_active:
                    transaction.rollback()
            responses = [future.result(timeout=10) for future in futures]

    assert sorted(response.response_status for response in responses) == [200, 409]
    success = next(response for response in responses if response.response_status == 200)
    conflict = next(response for response in responses if response.response_status == 409)
    assert success.response_json["status"] == "PENDING"
    _assert_error(conflict, 409, "CLI0002")

    after = _snapshot(api_database_engine, client_key)
    events = _events(api_database_engine, client_key)
    assert after["client_status"] == "PENDING"
    assert after["client_event_count"] == before["client_event_count"] + 1
    assert [(event["from_status"], event["to_status"]) for event in events[-1:]] == [
        ("REJECTED", "PENDING")
    ]
    assert not any(
        event["from_status"] == event["to_status"] == "PENDING"
        for event in events
    )


@pytest.mark.parametrize("first_operation", ["R04", "R09"])
def test_r09_and_r04_serialize_on_client_lock(
    api_database_engine: Engine,
    first_operation: str,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")

    def open_account():
        return ClientRequisition.send(
            "POST",
            f"/client/{client_key}/account",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

    operations = {
        "R04": open_account,
        "R09": lambda: _patch(client_key, "INACTIVE", "Concorrência R09/R04"),
    }
    second_operation = "R09" if first_operation == "R04" else "R04"

    with api_database_engine.connect() as lock_connection:
        transaction = lock_connection.begin()
        lock_connection.execute(
            text(
                """
                SELECT id FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                FOR UPDATE
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        with ThreadPoolExecutor(max_workers=2) as executor:
            first_future = executor.submit(operations[first_operation])
            try:
                _wait_for_blocked_request(lock_connection, f"CLIENT/{first_operation}")
                second_future = executor.submit(operations[second_operation])
            finally:
                if transaction.is_active:
                    transaction.rollback()
            first_response = first_future.result(timeout=10)
            second_response = second_future.result(timeout=10)

    responses = {
        first_operation: first_response,
        second_operation: second_response,
    }
    if first_operation == "R04":
        assert responses["R04"].response_status == 201
        _assert_error(responses["R09"], 409, "CLI0009")
        snapshot = _snapshot(api_database_engine, client_key)
        assert snapshot["client_status"] == "ACTIVE"
        assert snapshot["account_count"] == 1
    else:
        assert responses["R09"].response_status == 200
        _assert_error(responses["R04"], 409, "CLI0002")
        snapshot = _snapshot(api_database_engine, client_key)
        assert snapshot["client_status"] == "INACTIVE"
        assert snapshot["account_count"] == 0


def test_r09_revalidates_after_r03_wins_client_lock(
    api_database_engine: Engine,
) -> None:
    MockServer.reset()
    client_key, cpf = create_pending_individual()
    expected_request = provider_request(client_key, "INDIVIDUAL", cpf)
    expect_client_analysis(expected_request, "REJECT", "Rejeição concorrente")
    before = _snapshot(api_database_engine, client_key)

    with api_database_engine.connect() as lock_connection:
        transaction = lock_connection.begin()
        lock_connection.execute(
            text(
                """
                SELECT id FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                FOR UPDATE
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        with ThreadPoolExecutor(max_workers=2) as executor:
            analysis_future = executor.submit(analyze_client, client_key)
            try:
                _wait_for_blocked_request(lock_connection, "CLIENT/R03")
                reanalysis_future = executor.submit(
                    _patch,
                    client_key,
                    "PENDING",
                    "Reanálise após R03",
                )
            finally:
                if transaction.is_active:
                    transaction.rollback()
            analysis_response = analysis_future.result(timeout=10)
            reanalysis_response = reanalysis_future.result(timeout=10)

    assert analysis_response.response_status == 200
    assert analysis_response.response_json["status"] == "REJECTED"
    assert reanalysis_response.response_status == 200
    assert reanalysis_response.response_json["status"] == "PENDING"
    MockServer.verify_exactly(expected_request, count=1)
    after = _snapshot(api_database_engine, client_key)
    assert after["client_status"] == "PENDING"
    assert after["client_event_count"] == before["client_event_count"] + 2
    assert [(event["from_status"], event["to_status"]) for event in _events(
        api_database_engine, client_key
    )[-2:]] == [("PENDING", "REJECTED"), ("REJECTED", "PENDING")]
