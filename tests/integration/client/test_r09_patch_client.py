"""Integração do lifecycle direto de CLIENT pela R09."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from os import environ
from threading import Barrier
from time import monotonic, sleep
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from tests.utils import DbUtils, INTERNAL_TOKEN, RandomGenerator
from tests.utils.mockserver import MockServer
from tests.utils.requisition import ClientRequisition
from tests.integration.client.r03.support import (
    analyze_client,
    create_pending_individual,
    expect_client_analysis,
    provider_request,
)


@pytest.fixture(scope="module")
def api_database_engine() -> Iterator[Engine]:
    api_url = make_url(DbUtils.database_url())
    test_url = make_url(environ["TEST_DATABASE_URL"])
    assert api_url.database == "bootcamp"
    assert api_url.host in {"localhost", "127.0.0.1"}
    assert test_url.database == "bootcamp_test"
    assert test_url.host in {"localhost", "127.0.0.1"}
    assert api_url != test_url

    engine = create_engine(api_url)
    test_engine = create_engine(test_url)
    try:
        with engine.connect() as connection:
            api_identity = connection.execute(
                text("SELECT system_identifier::text FROM pg_control_system()")
            ).scalar_one()
        with test_engine.connect() as connection:
            test_identity = connection.execute(
                text("SELECT system_identifier::text FROM pg_control_system()")
            ).scalar_one()
        assert api_identity != test_identity
        yield engine
    finally:
        test_engine.dispose()
        engine.dispose()


def _create_client(client_type: str = "INDIVIDUAL") -> tuple[str, str]:
    email = f"r09.{client_type.lower()}.{uuid4()}@example.com"
    payload = {
        "client_type": client_type,
        "email": email,
        "timezone": "America/Sao_Paulo",
    }
    if client_type == "INDIVIDUAL":
        payload.update(
            cpf=RandomGenerator.generate_cpf(),
            full_name="Cliente R09",
            birth_date="1990-05-17",
        )
    else:
        payload.update(
            cnpj=RandomGenerator.generate_cnpj(),
            legal_name="Empresa R09 Ltda.",
            trade_name="Empresa R09",
        )

    response = ClientRequisition.send(
        "POST",
        "/client",
        payload=payload,
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert response.response_status == 201
    return response.response_json["client_key"], email


def _transition_client_fixture(
    engine: Engine,
    client_key: str,
    expected_status: str,
    target_status: str,
) -> None:
    with engine.begin() as connection:
        client = connection.execute(
            text(
                """
                SELECT client.id, client.status_id
                FROM client
                JOIN client_status AS status ON status.id = client.status_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                  AND status.enumerator = :expected_status
                """
            ),
            {"client_key": client_key, "expected_status": expected_status},
        ).mappings().one()
        changed_at = datetime.now(timezone.utc)
        updated = connection.execute(
            text(
                """
                UPDATE client
                SET status_id = (
                        SELECT id FROM client_status WHERE enumerator = :target_status
                    ),
                    updated_at = :changed_at
                WHERE id = :client_id AND status_id = :old_status_id
                """
            ),
            {
                "client_id": client["id"],
                "old_status_id": client["status_id"],
                "target_status": target_status,
                "changed_at": changed_at,
            },
        )
        assert updated.rowcount == 1
        inserted = connection.execute(
            text(
                """
                INSERT INTO client_status_event
                    (client_id, from_status_id, to_status_id, actor_type, reason, created_at)
                SELECT :client_id, :from_status_id, status.id,
                       'INTERNAL', :reason, :changed_at
                FROM client_status AS status
                WHERE status.enumerator = :target_status
                """
            ),
            {
                "client_id": client["id"],
                "from_status_id": client["status_id"],
                "target_status": target_status,
                "reason": f"Fixture {expected_status} para {target_status}",
                "changed_at": changed_at,
            },
        )
        assert inserted.rowcount == 1


def _create_client_in_status(
    engine: Engine,
    status: str,
    client_type: str = "INDIVIDUAL",
) -> tuple[str, str]:
    client_key, email = _create_client(client_type)
    if status in {"ACTIVE", "REJECTED"}:
        _transition_client_fixture(engine, client_key, "PENDING", status)
    elif status == "INACTIVE":
        _transition_client_fixture(engine, client_key, "PENDING", "ACTIVE")
        _transition_client_fixture(engine, client_key, "ACTIVE", "INACTIVE")
    elif status != "PENDING":
        raise AssertionError(f"Unsupported fixture status: {status}")
    return client_key, email


def _snapshot(engine: Engine, client_key: str) -> dict:
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        row = connection.execute(
            text(
                """
                SELECT client.id AS client_id, client.client_key::text AS client_key,
                       client.client_type, client.email, client.timezone,
                       client.created_at, client.updated_at,
                       status.enumerator AS client_status,
                       (SELECT COUNT(*) FROM client_status_event
                        WHERE client_id = client.id) AS client_event_count,
                       (SELECT COUNT(*) FROM account
                        WHERE client_id = client.id) AS account_count,
                       (SELECT COUNT(*) FROM account_status_event
                        JOIN account ON account.id = account_status_event.account_id
                        WHERE account.client_id = client.id) AS account_event_count,
                       (SELECT COUNT(*) FROM transaction_entry
                        JOIN account ON account.id = transaction_entry.account_id
                        WHERE account.client_id = client.id) AS entry_count,
                       (SELECT COUNT(DISTINCT financial_transaction.id)
                        FROM financial_transaction
                        JOIN transaction_entry
                          ON transaction_entry.transaction_id = financial_transaction.id
                        JOIN account ON account.id = transaction_entry.account_id
                        WHERE account.client_id = client.id) AS transaction_count,
                       (SELECT status.enumerator FROM account
                        JOIN account_status AS status ON status.id = account.status_id
                        WHERE account.client_id = client.id) AS account_status,
                       (SELECT account.balance_cents FROM account
                        WHERE account.client_id = client.id) AS balance_cents,
                       (SELECT account.updated_at FROM account
                        WHERE account.client_id = client.id) AS account_updated_at
                FROM client
                JOIN client_status AS status ON status.id = client.status_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).mappings().one()
        return dict(row)


def _events(engine: Engine, client_key: str) -> list[dict]:
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        rows = connection.execute(
            text(
                """
                SELECT source.enumerator AS from_status,
                       destination.enumerator AS to_status,
                       event.actor_type, event.reason, event.created_at
                FROM client_status_event AS event
                JOIN client ON client.id = event.client_id
                LEFT JOIN client_status AS source ON source.id = event.from_status_id
                JOIN client_status AS destination ON destination.id = event.to_status_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                ORDER BY event.id
                """
            ),
            {"client_key": client_key},
        ).mappings().all()
        return [dict(row) for row in rows]


def _patch(client_key: str, status: str, reason: str = "Motivo operacional"):
    return ClientRequisition.send(
        "PATCH",
        f"/client/{client_key}",
        payload={"status": status, "reason": reason},
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.response_status == status
    assert set(response.response_json) == {
        "title",
        "description",
        "translation",
        "code",
    }
    assert response.response_json["code"] == code


def _open_account(client_key: str, status: str = "ACTIVE") -> str:
    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert response.response_status == 201
    account_key = response.response_json["account_key"]
    if status != "ACTIVE":
        transition = ClientRequisition.send(
            "PATCH",
            f"/account/{account_key}",
            payload={"status": status, "reason": f"Fixture ACCOUNT {status}"},
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        assert transition.response_status == 200
    return account_key


@pytest.mark.parametrize(
    ("client_type", "initial_status", "target_status"),
    [
        ("INDIVIDUAL", "REJECTED", "PENDING"),
        ("INDIVIDUAL", "ACTIVE", "INACTIVE"),
        ("COMPANY", "INACTIVE", "ACTIVE"),
    ],
)
def test_patch_client_allowed_transitions_update_status_and_create_one_event(
    api_database_engine: Engine,
    client_type: str,
    initial_status: str,
    target_status: str,
) -> None:
    client_key, _ = _create_client_in_status(
        api_database_engine,
        initial_status,
        client_type,
    )
    before = _snapshot(api_database_engine, client_key)

    response = _patch(client_key, target_status, "  Solicitação operacional  ")

    assert response.response_status == 200
    assert response.response_json == {
        "client_key": client_key,
        "status": target_status,
    }
    after = _snapshot(api_database_engine, client_key)
    assert after["client_status"] == target_status
    assert after["client_event_count"] == before["client_event_count"] + 1
    assert after["account_count"] == before["account_count"] == 0
    assert after["client_type"] == before["client_type"] == client_type
    assert after["email"] == before["email"]
    assert after["timezone"] == before["timezone"]
    assert after["created_at"] == before["created_at"]
    assert after["updated_at"] > before["updated_at"]
    assert after["account_event_count"] == before["account_event_count"] == 0
    assert after["entry_count"] == before["entry_count"] == 0
    assert after["transaction_count"] == before["transaction_count"] == 0
    event = _events(api_database_engine, client_key)[-1]
    assert event["from_status"] == initial_status
    assert event["to_status"] == target_status
    assert event["actor_type"] == "INTERNAL"
    assert event["reason"] == "Solicitação operacional"
    assert event["created_at"] == after["updated_at"]
    assert event["created_at"].tzinfo is not None
    assert event["created_at"].utcoffset() == timezone.utc.utcoffset(
        event["created_at"]
    )


def test_patch_client_rejects_malformed_key() -> None:
    response = _patch("not-a-uuid", "INACTIVE")

    _assert_error(response, 400, "QIT000001")


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"reason": "Motivo"},
        {"status": None, "reason": "Motivo"},
        {"status": 1, "reason": "Motivo"},
        {"status": True, "reason": "Motivo"},
        {"status": "active", "reason": "Motivo"},
        {"status": "CLOSED", "reason": "Motivo"},
        {"status": "UNKNOWN", "reason": "Motivo"},
        {"status": "INACTIVE"},
        {"status": "INACTIVE", "reason": None},
        {"status": "INACTIVE", "reason": 1},
        {"status": "INACTIVE", "reason": ""},
        {"status": "INACTIVE", "reason": "   "},
        {"status": "INACTIVE", "reason": "X" * 501},
        {"status": "INACTIVE", "reason": "Motivo", "email": "novo@example.com"},
    ],
)
def test_patch_client_rejects_invalid_body(payload) -> None:
    response = ClientRequisition.send(
        "PATCH",
        f"/client/{uuid4()}",
        payload=payload,
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_error(response, 400, "QIT000001")


def test_patch_client_rejects_malformed_json() -> None:
    response = ClientRequisition.send(
        "PATCH",
        f"/client/{uuid4()}",
        data="{",
        headers={
            "INTERNAL-TOKEN": INTERNAL_TOKEN,
            "Content-Type": "application/json",
        },
    )
    _assert_error(response, 400, "QIT000001")


@pytest.mark.parametrize(
    ("client_key", "payload", "headers"),
    [
        (str(uuid4()), {"status": "INACTIVE", "reason": "Motivo"}, {}),
        (
            str(uuid4()),
            {"status": "INACTIVE", "reason": "Motivo"},
            {"INTERNAL-TOKEN": "invalid"},
        ),
        ("not-a-uuid", {"status": None}, {"INTERNAL-TOKEN": "invalid"}),
    ],
)
def test_patch_client_authentication_has_precedence(
    client_key: str,
    payload,
    headers: dict,
) -> None:
    response = ClientRequisition.send(
        "PATCH",
        f"/client/{client_key}",
        payload=payload,
        headers=headers,
    )
    _assert_error(response, 403, "QIT000002")


def test_patch_client_rejects_unknown_client() -> None:
    response = _patch(str(uuid4()), "INACTIVE")
    _assert_error(response, 404, "CLI0001")


@pytest.mark.parametrize(
    ("initial_status", "target_status"),
    [
        ("PENDING", "PENDING"),
        ("ACTIVE", "ACTIVE"),
        ("REJECTED", "REJECTED"),
        ("INACTIVE", "INACTIVE"),
        ("PENDING", "ACTIVE"),
        ("PENDING", "REJECTED"),
        ("REJECTED", "ACTIVE"),
        ("REJECTED", "INACTIVE"),
        ("ACTIVE", "PENDING"),
        ("ACTIVE", "REJECTED"),
        ("INACTIVE", "PENDING"),
        ("INACTIVE", "REJECTED"),
    ],
)
def test_patch_client_rejects_forbidden_transition_without_side_effects(
    api_database_engine: Engine,
    initial_status: str,
    target_status: str,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, initial_status)
    before = _snapshot(api_database_engine, client_key)

    response = _patch(client_key, target_status)

    _assert_error(response, 409, "CLI0002")
    assert _snapshot(api_database_engine, client_key) == before


@pytest.mark.parametrize("account_status", ["ACTIVE", "INACTIVE", "CLOSED"])
def test_patch_client_requires_r06_when_any_account_exists(
    api_database_engine: Engine,
    account_status: str,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")
    _open_account(client_key, account_status)
    before = _snapshot(api_database_engine, client_key)
    target_status = "INACTIVE" if account_status == "ACTIVE" else "ACTIVE"

    response = _patch(client_key, target_status)

    _assert_error(response, 409, "CLI0009")
    assert _snapshot(api_database_engine, client_key) == before


def test_patch_client_allows_reanalysis_without_artificial_limit(
    api_database_engine: Engine,
) -> None:
    MockServer.reset()
    client_key, _ = _create_client_in_status(api_database_engine, "REJECTED")
    first = _patch(client_key, "PENDING", " Primeira reanálise ")
    assert first.response_status == 200

    _transition_client_fixture(
        api_database_engine,
        client_key,
        "PENDING",
        "REJECTED",
    )
    before_second = _snapshot(api_database_engine, client_key)
    second = _patch(client_key, "PENDING", " Segunda reanálise ")

    assert second.response_status == 200
    assert second.response_json == {"client_key": client_key, "status": "PENDING"}
    after_second = _snapshot(api_database_engine, client_key)
    assert after_second["client_event_count"] == before_second["client_event_count"] + 1
    assert _events(api_database_engine, client_key)[-1]["reason"] == "Segunda reanálise"
    MockServer.verify_exactly(
        {"method": "POST", "path": "/v1/client-analysis"},
        count=0,
    )


def test_r02_reflects_status_changed_by_r09(api_database_engine: Engine) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")
    assert _patch(client_key, "INACTIVE").response_status == 200

    response = ClientRequisition.send(
        "GET",
        f"/client/{client_key}",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    assert response.response_status == 200
    assert response.response_json["status"] == "INACTIVE"


@pytest.mark.parametrize("reason", [" X ", f" {'R' * 500} "])
def test_patch_client_accepts_reason_boundaries_after_trimming(
    api_database_engine: Engine,
    reason: str,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")

    response = _patch(client_key, "INACTIVE", reason)

    assert response.response_status == 200
    assert _events(api_database_engine, client_key)[-1]["reason"] == reason.strip()


def _wait_for_blocked_request(connection, resource: str) -> None:
    blocker_pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
    deadline = monotonic() + 5
    while monotonic() < deadline:
        connection.execute(text("SELECT pg_stat_clear_snapshot()"))
        waiting = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_stat_activity AS activity
                WHERE activity.datname = current_database()
                  AND activity.wait_event_type = 'Lock'
                  AND :blocker_pid = ANY(pg_blocking_pids(activity.pid))
                """
            ),
            {"blocker_pid": blocker_pid},
        ).scalar_one()
        if waiting:
            return
        sleep(0.01)
    raise AssertionError(
        f"Nenhuma request aguardou o lock do backend {blocker_pid} em {resource}"
    )


@contextmanager
def _reject_status_event_for_client(
    engine: Engine,
    client_key: str,
) -> Iterator[None]:
    suffix = uuid4().hex
    function_name = f"r09_fail_event_function_{suffix}"
    trigger_name = f"r09_fail_event_trigger_{suffix}"
    with engine.begin() as connection:
        client_id = connection.execute(
            text(
                """
                SELECT id FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF NEW.client_id = {client_id} THEN
                    RAISE EXCEPTION 'R09 controlled event failure';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON client_status_event
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON client_status_event"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )


def test_patch_client_rolls_back_when_status_event_insert_fails(
    api_database_engine: Engine,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")
    before = _snapshot(api_database_engine, client_key)

    with _reject_status_event_for_client(api_database_engine, client_key):
        response = _patch(client_key, "INACTIVE", "Falha controlada")

    _assert_error(response, 500, "QIT000500")
    assert _snapshot(api_database_engine, client_key) == before


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


def test_r09_refusal_preserves_r06_as_account_lifecycle_authority(
    api_database_engine: Engine,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")
    account_key = _open_account(client_key)
    direct = _patch(client_key, "INACTIVE", "Tentativa direta")
    _assert_error(direct, 409, "CLI0009")

    coordinated = ClientRequisition.send(
        "PATCH",
        f"/account/{account_key}",
        payload={"status": "INACTIVE", "reason": "Lifecycle coordenado"},
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    assert coordinated.response_status == 200
    after = _snapshot(api_database_engine, client_key)
    assert (after["client_status"], after["account_status"]) == (
        "INACTIVE",
        "INACTIVE",
    )
