"""Integração do lifecycle coordenado de ACCOUNT e CLIENT."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from os import environ
from threading import Barrier
from time import monotonic, sleep
from uuid import uuid4

import pytest
from psycopg2.errors import LockNotAvailable
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.exc import OperationalError

from tests.utils import DbUtils, INTERNAL_TOKEN, RandomGenerator
from tests.utils.requisition import ClientRequisition


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
                text("SELECT (SELECT system_identifier::text FROM pg_control_system())")
            ).scalar_one()
        with test_engine.connect() as connection:
            test_identity = connection.execute(
                text("SELECT (SELECT system_identifier::text FROM pg_control_system())")
            ).scalar_one()
        assert api_identity != test_identity
        yield engine
    finally:
        test_engine.dispose()
        engine.dispose()


def _create_active_account(engine: Engine, client_type: str = "INDIVIDUAL") -> tuple[str, str]:
    email = f"r06.{client_type.lower()}.{uuid4()}@example.com"
    payload = {
        "client_type": client_type,
        "email": email,
        "timezone": "America/Sao_Paulo",
    }
    if client_type == "INDIVIDUAL":
        payload.update(
            cpf=RandomGenerator.generate_cpf(),
            full_name="Cliente R06",
            birth_date="1990-05-17",
        )
    else:
        payload.update(
            cnpj=RandomGenerator.generate_cnpj(),
            legal_name="Empresa R06 Ltda.",
            trade_name="Empresa R06",
        )

    client_response = ClientRequisition.send(
        "POST", "/client", payload=payload, headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )
    assert client_response.response_status == 201
    client_key = client_response.response_json["client_key"]

    with engine.begin() as connection:
        client = connection.execute(
            text(
                """
                SELECT client.id, client.status_id
                FROM client
                JOIN client_status AS status ON status.id = client.status_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                  AND status.enumerator = 'PENDING'
                """
            ),
            {"client_key": client_key},
        ).mappings().one()
        changed_at = datetime.now(timezone.utc)
        assert connection.execute(
            text(
                """
                UPDATE client
                SET status_id = (SELECT id FROM client_status WHERE enumerator = 'ACTIVE'),
                    updated_at = :changed_at
                WHERE id = :client_id AND status_id = :old_status_id
                """
            ),
            {"client_id": client["id"], "old_status_id": client["status_id"], "changed_at": changed_at},
        ).rowcount == 1
        assert connection.execute(
            text(
                """
                INSERT INTO client_status_event
                    (client_id, from_status_id, to_status_id, actor_type, reason, created_at)
                SELECT :client_id, :from_status_id, status.id, 'INTERNAL', NULL, :changed_at
                FROM client_status AS status WHERE status.enumerator = 'ACTIVE'
                """
            ),
            {"client_id": client["id"], "from_status_id": client["status_id"], "changed_at": changed_at},
        ).rowcount == 1

    account_response = ClientRequisition.send(
        "POST", f"/client/{client_key}/account", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )
    assert account_response.response_status == 201
    return client_key, account_response.response_json["account_key"]


def _snapshot(engine: Engine, account_key: str) -> dict:
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        row = connection.execute(
            text(
                """
                SELECT account.id AS account_id, client.id AS client_id,
                       account.account_key::text AS account_key,
                       client.client_key::text AS client_key,
                       account_status.enumerator AS account_status,
                       client_status.enumerator AS client_status,
                       account.balance_cents, account.created_at AS account_created_at,
                       account.updated_at AS account_updated_at,
                       client.created_at AS client_created_at,
                       client.updated_at AS client_updated_at,
                       (SELECT COUNT(*) FROM account_status_event
                        WHERE account_id = account.id) AS account_event_count,
                       (SELECT COUNT(*) FROM client_status_event
                        WHERE client_id = client.id) AS client_event_count,
                       (SELECT COUNT(*) FROM transaction_entry
                        WHERE account_id = account.id) AS entry_count,
                       (SELECT COUNT(DISTINCT financial_transaction.id)
                        FROM transaction_entry
                        JOIN financial_transaction
                          ON financial_transaction.id = transaction_entry.transaction_id
                        WHERE transaction_entry.account_id = account.id) AS transaction_count
                FROM account
                JOIN client ON client.id = account.client_id
                JOIN account_status ON account_status.id = account.status_id
                JOIN client_status ON client_status.id = client.status_id
                WHERE account.account_key = CAST(:account_key AS uuid)
                """
            ),
            {"account_key": account_key},
        ).mappings().one()
        return dict(row)


def _events(engine: Engine, account_key: str) -> tuple[list[dict], list[dict]]:
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        account_events = connection.execute(
            text(
                """
                SELECT source.enumerator AS from_status, destination.enumerator AS to_status,
                       event.actor_type, event.reason, event.created_at
                FROM account_status_event AS event
                JOIN account ON account.id = event.account_id
                LEFT JOIN account_status AS source ON source.id = event.from_status_id
                JOIN account_status AS destination ON destination.id = event.to_status_id
                WHERE account.account_key = CAST(:account_key AS uuid)
                ORDER BY event.id
                """
            ),
            {"account_key": account_key},
        ).mappings().all()
        client_events = connection.execute(
            text(
                """
                SELECT source.enumerator AS from_status, destination.enumerator AS to_status,
                       event.actor_type, event.reason, event.created_at
                FROM client_status_event AS event
                JOIN client ON client.id = event.client_id
                JOIN account ON account.client_id = client.id
                LEFT JOIN client_status AS source ON source.id = event.from_status_id
                JOIN client_status AS destination ON destination.id = event.to_status_id
                WHERE account.account_key = CAST(:account_key AS uuid)
                ORDER BY event.id
                """
            ),
            {"account_key": account_key},
        ).mappings().all()
        return [dict(row) for row in account_events], [dict(row) for row in client_events]


def _assert_error(response, status: int, code: str) -> None:
    assert response.response_status == status
    assert set(response.response_json) == {"title", "description", "translation", "code"}
    assert response.response_json["code"] == code


def _patch(account_key: str, status: str, reason: str = "Motivo operacional"):
    return ClientRequisition.send(
        "PATCH",
        f"/account/{account_key}",
        payload={"status": status, "reason": reason},
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )


def _prepare_inactive(account_key: str) -> None:
    response = _patch(account_key, "INACTIVE", "Preparação INACTIVE")
    assert response.response_status == 200


def _set_balance(engine: Engine, account_key: str, balance_cents: int) -> None:
    with engine.begin() as connection:
        assert connection.execute(
            text(
                """
                UPDATE account SET balance_cents = :balance_cents
                WHERE account_key = CAST(:account_key AS uuid)
                """
            ),
            {"account_key": account_key, "balance_cents": balance_cents},
        ).rowcount == 1


def _force_client_status(engine: Engine, account_key: str, status: str) -> None:
    with engine.begin() as connection:
        assert connection.execute(
            text(
                """
                UPDATE client
                SET status_id = (SELECT id FROM client_status WHERE enumerator = :status)
                WHERE id = (
                    SELECT client_id FROM account
                    WHERE account_key = CAST(:account_key AS uuid)
                )
                """
            ),
            {"account_key": account_key, "status": status},
        ).rowcount == 1


def _wait_for_blocked_request(connection, resource: str) -> None:
    blocker_pid = connection.execute(text("SELECT pg_backend_pid()")).scalar_one()
    deadline = monotonic() + 5
    while monotonic() < deadline:
        connection.execute(text("SELECT pg_stat_clear_snapshot()"))
        waiting = connection.execute(
            text(
                """
                SELECT COUNT(*) FROM pg_stat_activity AS activity
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
def _reject_status_event_for_account(
    engine: Engine,
    account_key: str,
    event_table: str,
) -> Iterator[None]:
    assert event_table in {"account_status_event", "client_status_event"}
    suffix = uuid4().hex
    function_name = f"r06_fail_event_function_{suffix}"
    trigger_name = f"r06_fail_event_trigger_{suffix}"
    with engine.begin() as connection:
        owner = connection.execute(
            text(
                """
                SELECT account.id AS account_id, account.client_id
                FROM account
                WHERE account.account_key = CAST(:account_key AS uuid)
                """
            ),
            {"account_key": account_key},
        ).mappings().one()
        owner_column = "account_id" if event_table == "account_status_event" else "client_id"
        owner_id = owner[owner_column]
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF NEW.{owner_column} = {owner_id} THEN
                    RAISE EXCEPTION 'R06 controlled event failure';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON {event_table}
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON {event_table}"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )


def test_patch_account_active_to_inactive_updates_both_resources(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    before = _snapshot(api_database_engine, account_key)

    response = ClientRequisition.send(
        "PATCH",
        f"/account/{account_key}",
        payload={"status": "INACTIVE", "reason": "  Solicitação operacional  "},
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    assert response.response_status == 200
    assert response.response_json == {"account_key": account_key, "status": "INACTIVE"}
    after = _snapshot(api_database_engine, account_key)
    assert after["account_status"] == "INACTIVE"
    assert after["client_status"] == "INACTIVE"
    assert after["balance_cents"] == before["balance_cents"]
    assert after["account_created_at"] == before["account_created_at"]
    assert after["client_created_at"] == before["client_created_at"]
    assert after["account_updated_at"] == after["client_updated_at"]
    assert after["entry_count"] == before["entry_count"] == 0
    assert after["transaction_count"] == before["transaction_count"] == 0
    assert after["account_event_count"] == before["account_event_count"] + 1
    assert after["client_event_count"] == before["client_event_count"] + 1
    account_events, client_events = _events(api_database_engine, account_key)
    account_event = account_events[-1]
    client_event = client_events[-1]
    for event in (account_event, client_event):
        assert event["from_status"] == "ACTIVE"
        assert event["to_status"] == "INACTIVE"
        assert event["actor_type"] == "INTERNAL"
        assert event["reason"] == "Solicitação operacional"
        assert event["created_at"].tzinfo is not None
        assert event["created_at"].utcoffset() == timezone.utc.utcoffset(event["created_at"])


def test_patch_account_rejects_malformed_key() -> None:
    response = ClientRequisition.send(
        "PATCH",
        "/account/not-a-uuid",
        payload={"status": "INACTIVE", "reason": "Motivo"},
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_error(response, 400, "QIT000001")


def test_patch_company_account_inactive_to_active_accepts_500_character_reason(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine, "COMPANY")
    _prepare_inactive(account_key)
    before = _snapshot(api_database_engine, account_key)
    reason = "R" * 500

    response = _patch(account_key, "ACTIVE", f" {reason} ")

    assert response.response_status == 200
    assert response.response_json == {"account_key": account_key, "status": "ACTIVE"}
    after = _snapshot(api_database_engine, account_key)
    assert (after["account_status"], after["client_status"]) == ("ACTIVE", "ACTIVE")
    assert after["account_event_count"] == before["account_event_count"] + 1
    assert after["client_event_count"] == before["client_event_count"] + 1
    account_events, client_events = _events(api_database_engine, account_key)
    assert account_events[-1]["reason"] == reason
    assert client_events[-1]["reason"] == reason


def test_patch_account_active_to_closed_closes_account_and_inactivates_client(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    before = _snapshot(api_database_engine, account_key)

    response = _patch(account_key, "CLOSED", "Encerramento solicitado")

    assert response.response_status == 200
    assert response.response_json == {"account_key": account_key, "status": "CLOSED"}
    after = _snapshot(api_database_engine, account_key)
    assert (after["account_status"], after["client_status"]) == ("CLOSED", "INACTIVE")
    assert after["account_event_count"] == before["account_event_count"] + 1
    assert after["client_event_count"] == before["client_event_count"] + 1
    assert after["balance_cents"] == 0
    assert after["account_created_at"] == before["account_created_at"]
    assert after["client_created_at"] == before["client_created_at"]


def test_patch_account_inactive_to_closed_does_not_create_same_state_client_event(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    _prepare_inactive(account_key)
    before = _snapshot(api_database_engine, account_key)

    response = _patch(account_key, "CLOSED", "Encerramento definitivo")

    assert response.response_status == 200
    after = _snapshot(api_database_engine, account_key)
    assert (after["account_status"], after["client_status"]) == ("CLOSED", "INACTIVE")
    assert after["account_event_count"] == before["account_event_count"] + 1
    assert after["client_event_count"] == before["client_event_count"]
    assert after["client_updated_at"] == before["client_updated_at"]


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"reason": "Motivo"},
        {"status": None, "reason": "Motivo"},
        {"status": 1, "reason": "Motivo"},
        {"status": "active", "reason": "Motivo"},
        {"status": "INVALID", "reason": "Motivo"},
        {"status": "INACTIVE"},
        {"status": "INACTIVE", "reason": None},
        {"status": "INACTIVE", "reason": 1},
        {"status": "INACTIVE", "reason": ""},
        {"status": "INACTIVE", "reason": "   "},
        {"status": "INACTIVE", "reason": "X" * 501},
        {"status": "INACTIVE", "reason": "Motivo", "balance_cents": 0},
    ],
)
def test_patch_account_rejects_invalid_body(payload) -> None:
    response = ClientRequisition.send(
        "PATCH",
        f"/account/{uuid4()}",
        payload=payload,
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_error(response, 400, "QIT000001")


def test_patch_account_rejects_malformed_json() -> None:
    response = ClientRequisition.send(
        "PATCH",
        f"/account/{uuid4()}",
        data="{",
        headers={
            "INTERNAL-TOKEN": INTERNAL_TOKEN,
            "Content-Type": "application/json",
        },
    )
    _assert_error(response, 400, "QIT000001")


@pytest.mark.parametrize(
    ("account_key", "payload", "headers"),
    [
        (str(uuid4()), {"status": "INACTIVE", "reason": "Motivo"}, {}),
        (str(uuid4()), {"status": "INACTIVE", "reason": "Motivo"}, {"INTERNAL-TOKEN": "invalid"}),
        ("not-a-uuid", {"status": None}, {"INTERNAL-TOKEN": "invalid"}),
    ],
)
def test_patch_account_authentication_has_precedence(account_key, payload, headers) -> None:
    response = ClientRequisition.send(
        "PATCH", f"/account/{account_key}", payload=payload, headers=headers
    )
    _assert_error(response, 403, "QIT000002")


def test_patch_account_rejects_unknown_account_and_client_key() -> None:
    unknown = _patch(str(uuid4()), "INACTIVE")
    _assert_error(unknown, 404, "ACC0001")

    client_key, _ = _create_active_account_for_client_key_test()
    wrong_resource = _patch(client_key, "INACTIVE")
    _assert_error(wrong_resource, 404, "ACC0001")


def _create_active_account_for_client_key_test() -> tuple[str, str]:
    email = f"r06.wrong.resource.{uuid4()}@example.com"
    response = ClientRequisition.send(
        "POST",
        "/client",
        payload={
            "client_type": "INDIVIDUAL",
            "email": email,
            "cpf": RandomGenerator.generate_cpf(),
            "full_name": "Cliente Chave R06",
            "birth_date": "1990-05-17",
            "timezone": "America/Sao_Paulo",
        },
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert response.response_status == 201
    return response.response_json["client_key"], email


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


def test_r05_reflects_status_changed_by_r06(api_database_engine: Engine) -> None:
    _, account_key = _create_active_account(api_database_engine)
    assert _patch(account_key, "INACTIVE").response_status == 200

    response = ClientRequisition.send(
        "GET", f"/account/{account_key}", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )

    assert response.response_status == 200
    assert response.response_json["status"] == "INACTIVE"


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
