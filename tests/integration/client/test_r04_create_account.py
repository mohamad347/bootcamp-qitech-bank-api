"""Integração da abertura de conta para um CLIENT ACTIVE."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import datetime, timezone
from os import environ
from threading import Barrier
from time import monotonic, sleep
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from tests.utils import DbUtils, INTERNAL_TOKEN, RandomGenerator
from tests.utils.requisition import ClientRequisition


ACCOUNT_RESPONSE_FIELDS = {"account_key", "status", "balance_cents"}
INVALID_CLIENT_KEY_ERROR = {
    "title": "Bad Request",
    "description": "client_key must be a valid UUID",
    "translation": "Payload Inválido",
    "code": "QIT000001",
}
FORBIDDEN_ERROR = {
    "title": "Forbidden",
    "description": "Request must be internal",
    "translation": "Requisição precisa ser interna",
    "code": "QIT000002",
}
ACCOUNT_ALREADY_EXISTS_ERROR = {
    "title": "Client already has an account",
    "description": "The client already has an account.",
    "translation": "O cliente já possui uma conta.",
    "code": "ACC0002",
}
INTERNAL_ERROR = {
    "title": "Internal Error",
    "description": "An internal error has occurred and its being investigated.",
    "translation": "Um erro interno aconteceu e está sendo investigado.",
    "code": "QIT000500",
}


def _assert_created_account_response(response, client_key: str) -> None:
    assert response.response_status == 201
    assert response.response.headers["content-type"].startswith("application/json")

    response_body = response.response_json
    assert isinstance(response_body, dict)
    assert set(response_body) == ACCOUNT_RESPONSE_FIELDS
    assert isinstance(UUID(response_body["account_key"]), UUID)
    assert response_body["account_key"] != client_key
    assert response_body["status"] == "ACTIVE"
    assert type(response_body["balance_cents"]) is int
    assert response_body["balance_cents"] == 0


@pytest.fixture(scope="module")
def api_database_engine() -> Iterator[Engine]:
    """Conecta apenas ao banco local da API, distinto do banco de schema."""
    api_url = make_url(DbUtils.database_url())
    test_url = make_url(environ["TEST_DATABASE_URL"])

    assert api_url.database == "bootcamp"
    assert api_url.host in {"localhost", "127.0.0.1"}
    assert api_url.port == 5432
    assert test_url.database == "bootcamp_test"
    assert test_url.host in {"localhost", "127.0.0.1"}
    assert test_url.port == 5433
    assert api_url != test_url

    engine = create_engine(api_url)
    try:
        with engine.connect() as connection:
            api_identity = connection.execute(
                text(
                    "SELECT current_database(), "
                    "(SELECT system_identifier::text FROM pg_control_system()), "
                    "inet_server_port()"
                )
            ).one()

        assert api_identity[0] == "bootcamp"
        assert api_identity[1]
        assert api_identity[2] == 5432

        test_engine = create_engine(test_url)
        try:
            with test_engine.connect() as connection:
                test_identity = connection.execute(
                    text(
                        "SELECT current_database(), "
                        "(SELECT system_identifier::text FROM pg_control_system()), "
                        "inet_server_port()"
                    )
                ).one()
        finally:
            test_engine.dispose()

        assert test_identity[0] == "bootcamp_test"
        assert test_identity[1]
        assert test_identity[2] == 5432
        assert api_identity[1] != test_identity[1]

        yield engine
    finally:
        engine.dispose()


def _prepare_client_as_active(
    engine: Engine,
    client_key: str,
    expected_email: str,
    expected_client_type: str,
) -> None:
    """Transiciona somente o CLIENT recém-criado e registra seu evento."""
    with engine.begin() as connection:
        client = connection.execute(
            text(
                """
                SELECT c.id, c.email, c.client_type, s.id AS status_id,
                       s.enumerator AS status
                FROM client AS c
                JOIN client_status AS s ON s.id = c.status_id
                WHERE c.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).mappings().one()

        assert client["email"] == expected_email
        assert client["client_type"] == expected_client_type
        assert client["status"] == "PENDING"

        initial_event = connection.execute(
            text(
                """
                SELECT e.from_status_id, destination.enumerator AS to_status,
                       e.actor_type, e.reason
                FROM client_status_event AS e
                JOIN client_status AS destination
                  ON destination.id = e.to_status_id
                WHERE e.client_id = :client_id
                """
            ),
            {"client_id": client["id"]},
        ).mappings().all()
        assert len(initial_event) == 1
        assert initial_event[0]["from_status_id"] is None
        assert initial_event[0]["to_status"] == "PENDING"
        assert initial_event[0]["actor_type"] == "SYSTEM"
        assert initial_event[0]["reason"] is None

        assert connection.execute(
            text("SELECT id FROM client_status WHERE enumerator = 'ACTIVE'")
        ).scalar_one()

        account_count = connection.execute(
            text("SELECT COUNT(*) FROM account WHERE client_id = :client_id"),
            {"client_id": client["id"]},
        ).scalar_one()
        assert account_count == 0

        transition_time = datetime.now(timezone.utc)
        update_result = connection.execute(
            text(
                """
                UPDATE client
                SET status_id = (
                    SELECT id FROM client_status WHERE enumerator = 'ACTIVE'
                ), updated_at = :updated_at
                WHERE id = :client_id AND client_key = CAST(:client_key AS uuid)
                  AND status_id = :previous_status_id
                """
            ),
            {
                "updated_at": transition_time,
                "client_id": client["id"],
                "client_key": client_key,
                "previous_status_id": client["status_id"],
            },
        )
        assert update_result.rowcount == 1

        event_result = connection.execute(
            text(
                """
                INSERT INTO client_status_event (
                    client_id, from_status_id, to_status_id,
                    actor_type, reason, created_at
                )
                SELECT :client_id, :from_status_id, destination.id,
                       'INTERNAL', NULL, :created_at
                FROM client_status AS destination
                WHERE destination.enumerator = 'ACTIVE'
                """
            ),
            {
                "client_id": client["id"],
                "from_status_id": client["status_id"],
                "created_at": transition_time,
            },
        )
        assert event_result.rowcount == 1

        current_status = connection.execute(
            text(
                """
                SELECT status.enumerator
                FROM client
                JOIN client_status AS status ON status.id = client.status_id
                WHERE client.id = :client_id
                """
            ),
            {"client_id": client["id"]},
        ).scalar_one()
        assert current_status == "ACTIVE"

        event_count = connection.execute(
            text("SELECT COUNT(*) FROM client_status_event WHERE client_id = :client_id"),
            {"client_id": client["id"]},
        ).scalar_one()
        assert event_count == 2

        transition_event = connection.execute(
            text(
                """
                SELECT source.enumerator AS from_status,
                       destination.enumerator AS to_status,
                       event.actor_type, event.reason
                FROM client_status_event AS event
                LEFT JOIN client_status AS source
                  ON source.id = event.from_status_id
                JOIN client_status AS destination
                  ON destination.id = event.to_status_id
                WHERE event.client_id = :client_id
                  AND event.from_status_id IS NOT NULL
                """
            ),
            {"client_id": client["id"]},
        ).mappings().one()
        assert transition_event["from_status"] == "PENDING"
        assert transition_event["to_status"] == "ACTIVE"
        assert transition_event["actor_type"] == "INTERNAL"
        assert transition_event["reason"] is None


def _transition_client_status(
    engine: Engine,
    client_key: str,
    expected_email: str,
    expected_client_type: str,
    expected_status: str,
    next_status: str,
    reason: str,
) -> None:
    """Prepara uma transição de CLIENT exclusiva para o cenário de teste."""
    with engine.begin() as connection:
        client = connection.execute(
            text(
                """
                SELECT c.id, c.email, c.client_type, c.status_id,
                       status.enumerator AS status
                FROM client AS c
                JOIN client_status AS status ON status.id = c.status_id
                WHERE c.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).mappings().one()

        assert client["email"] == expected_email
        assert client["client_type"] == expected_client_type
        assert client["status"] == expected_status
        assert connection.execute(
            text("SELECT COUNT(*) FROM account WHERE client_id = :client_id"),
            {"client_id": client["id"]},
        ).scalar_one() == 0

        next_status_id = connection.execute(
            text("SELECT id FROM client_status WHERE enumerator = :status"),
            {"status": next_status},
        ).scalar_one()
        transition_time = datetime.now(timezone.utc)
        update_result = connection.execute(
            text(
                """
                UPDATE client
                SET status_id = :next_status_id, updated_at = :updated_at
                WHERE id = :client_id
                  AND client_key = CAST(:client_key AS uuid)
                  AND status_id = :previous_status_id
                """
            ),
            {
                "next_status_id": next_status_id,
                "updated_at": transition_time,
                "client_id": client["id"],
                "client_key": client_key,
                "previous_status_id": client["status_id"],
            },
        )
        assert update_result.rowcount == 1

        event_result = connection.execute(
            text(
                """
                INSERT INTO client_status_event (
                    client_id, from_status_id, to_status_id,
                    actor_type, reason, created_at
                ) VALUES (
                    :client_id, :from_status_id, :to_status_id,
                    'INTERNAL', :reason, :created_at
                )
                """
            ),
            {
                "client_id": client["id"],
                "from_status_id": client["status_id"],
                "to_status_id": next_status_id,
                "reason": reason,
                "created_at": transition_time,
            },
        )
        assert event_result.rowcount == 1


def _get_client_account_summary(engine: Engine, client_key: str) -> dict:
    """Lê somente o estado físico ligado ao CLIENT do cenário."""
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        client = connection.execute(
            text(
                """
                SELECT status.enumerator AS status
                FROM client
                JOIN client_status AS status ON status.id = client.status_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).mappings().one()
        account_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM account
                JOIN client ON client.id = account.client_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        account_status = connection.execute(
            text(
                """
                SELECT status.enumerator
                FROM account
                JOIN account_status AS status ON status.id = account.status_id
                JOIN client ON client.id = account.client_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one_or_none()
        account_event_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM account_status_event AS event
                JOIN account ON account.id = event.account_id
                JOIN client ON client.id = account.client_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        client_event_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM client_status_event AS event
                JOIN client ON client.id = event.client_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()

    return {
        "status": client["status"],
        "account_count": account_count,
        "account_status": account_status,
        "account_event_count": account_event_count,
        "client_event_count": client_event_count,
    }


def _expected_client_not_found_error(client_key: str) -> dict[str, str]:
    return {
        "title": "Client not found",
        "description": f"Client with key {client_key} was not found.",
        "translation": "O cliente informado não foi encontrado.",
        "code": "CLI0001",
    }


def _expected_invalid_client_status_error(current_status: str) -> dict[str, str]:
    return {
        "title": "Client status conflict",
        "description": (
            f"Client with status {current_status} cannot perform an operation "
            "that requires status ACTIVE."
        ),
        "translation": (
            f"O cliente com status {current_status} não pode executar uma "
            "operação que exige o status ACTIVE."
        ),
        "code": "CLI0002",
    }


def _assert_error_response(
    response,
    status_code: int,
    expected_body: dict[str, str],
) -> None:
    assert response.response_status == status_code
    assert response.response_json == expected_body


def _create_pending_individual() -> tuple[str, str]:
    email = f"r04.account.error.{uuid4()}@example.com"
    response = ClientRequisition.send(
        "POST",
        "/client",
        payload={
            "client_type": "INDIVIDUAL",
            "email": email,
            "cpf": RandomGenerator.generate_cpf(),
            "full_name": "Cliente R04 Erro",
            "birth_date": "1990-05-17",
            "timezone": "America/Sao_Paulo",
        },
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert response.response_status == 201
    return response.response_json["client_key"], email


def _close_account_and_inactivate_client(engine: Engine, client_key: str) -> None:
    """Prepara o histórico F02 ACTIVE/ACTIVE -> INACTIVE/CLOSED."""
    with engine.begin() as connection:
        persisted = connection.execute(
            text(
                """
                SELECT client.id AS client_id, client.status_id AS client_status_id,
                       account.id AS account_id, account.status_id AS account_status_id,
                       account.balance_cents
                FROM client
                JOIN account ON account.client_id = client.id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).mappings().one()
        assert persisted["balance_cents"] == 0

        statuses = connection.execute(
            text(
                """
                SELECT enumerator, id
                FROM client_status
                WHERE enumerator IN ('ACTIVE', 'INACTIVE')
                """
            )
        ).mappings().all()
        client_status_ids = {status["enumerator"]: status["id"] for status in statuses}
        account_status_ids = {
            status["enumerator"]: status["id"]
            for status in connection.execute(
                text(
                    """
                    SELECT enumerator, id
                    FROM account_status
                    WHERE enumerator IN ('ACTIVE', 'CLOSED')
                    """
                )
            ).mappings()
        }
        assert persisted["client_status_id"] == client_status_ids["ACTIVE"]
        assert persisted["account_status_id"] == account_status_ids["ACTIVE"]

        transition_time = datetime.now(timezone.utc)
        reason = "Encerramento controlado do cenário R04"
        account_update = connection.execute(
            text(
                """
                UPDATE account
                SET status_id = :closed_status_id, updated_at = :updated_at
                WHERE id = :account_id AND status_id = :active_status_id
                """
            ),
            {
                "closed_status_id": account_status_ids["CLOSED"],
                "updated_at": transition_time,
                "account_id": persisted["account_id"],
                "active_status_id": account_status_ids["ACTIVE"],
            },
        )
        assert account_update.rowcount == 1
        account_event = connection.execute(
            text(
                """
                INSERT INTO account_status_event (
                    account_id, from_status_id, to_status_id,
                    actor_type, reason, created_at
                ) VALUES (
                    :account_id, :from_status_id, :to_status_id,
                    'INTERNAL', :reason, :created_at
                )
                """
            ),
            {
                "account_id": persisted["account_id"],
                "from_status_id": account_status_ids["ACTIVE"],
                "to_status_id": account_status_ids["CLOSED"],
                "reason": reason,
                "created_at": transition_time,
            },
        )
        assert account_event.rowcount == 1
        client_update = connection.execute(
            text(
                """
                UPDATE client
                SET status_id = :inactive_status_id, updated_at = :updated_at
                WHERE id = :client_id AND status_id = :active_status_id
                """
            ),
            {
                "inactive_status_id": client_status_ids["INACTIVE"],
                "updated_at": transition_time,
                "client_id": persisted["client_id"],
                "active_status_id": client_status_ids["ACTIVE"],
            },
        )
        assert client_update.rowcount == 1
        client_event = connection.execute(
            text(
                """
                INSERT INTO client_status_event (
                    client_id, from_status_id, to_status_id,
                    actor_type, reason, created_at
                ) VALUES (
                    :client_id, :from_status_id, :to_status_id,
                    'INTERNAL', :reason, :created_at
                )
                """
            ),
            {
                "client_id": persisted["client_id"],
                "from_status_id": client_status_ids["ACTIVE"],
                "to_status_id": client_status_ids["INACTIVE"],
                "reason": reason,
                "created_at": transition_time,
            },
        )
        assert client_event.rowcount == 1


def _wait_for_client_lock_wait(
    connection,
    client_key: str,
) -> None:
    """Confirma que a request concorrente alcançou o lock da linha CLIENT."""
    deadline = monotonic() + 5
    while monotonic() < deadline:
        waiting_connections = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_stat_activity
                WHERE datname = current_database()
                  AND pid <> pg_backend_pid()
                  AND wait_event_type = 'Lock'
                  AND query LIKE '%FOR UPDATE OF client%'
                  AND query LIKE '%client%'
                """
            )
        ).scalar_one()
        if waiting_connections >= 1:
            return
        sleep(0.01)

    raise AssertionError(
        f"Nenhuma request ficou bloqueada no CLIENT {client_key} durante o teste"
    )


@contextmanager
def _reject_account_initial_event_for_client(
    engine: Engine,
    client_key: str,
) -> Iterator[None]:
    """Injeta uma falha temporária e localizada antes do evento de ACCOUNT."""
    suffix = uuid4().hex
    function_name = f"r04_fail_account_event_function_{suffix}"
    trigger_name = f"r04_fail_account_event_trigger_{suffix}"

    with engine.begin() as connection:
        client_id = connection.execute(
            text(
                """
                SELECT id
                FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM account
                    WHERE id = NEW.account_id AND client_id = {client_id}
                ) THEN
                    RAISE EXCEPTION 'Falha controlada no evento da R04';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON account_status_event
            FOR EACH ROW
            EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON account_status_event"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )


@contextmanager
def _raise_account_client_unique_violation_for_client(
    engine: Engine,
    client_key: str,
) -> Iterator[None]:
    """Simula somente a UniqueViolation final de ACCOUNT.client_id."""
    suffix = uuid4().hex
    function_name = f"r04_unique_account_function_{suffix}"
    trigger_name = f"r04_unique_account_trigger_{suffix}"

    with engine.begin() as connection:
        client_id = connection.execute(
            text(
                """
                SELECT id
                FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.client_id = {client_id} THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23505',
                        CONSTRAINT = 'account_client_id_key',
                        MESSAGE = 'Falha controlada de unicidade da R04';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON account
            FOR EACH ROW
            EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON account"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )


def test_create_account_for_active_individual_returns_201(
    api_database_engine: Engine,
) -> None:
    email = f"r04.account.{uuid4()}@example.com"
    client_payload = {
        "client_type": "INDIVIDUAL",
        "email": email,
        "cpf": RandomGenerator.generate_cpf(),
        "full_name": "Cliente R04 Teste",
        "birth_date": "1990-05-17",
        "timezone": "America/Sao_Paulo",
    }

    client_response = ClientRequisition.send(
        "POST",
        "/client",
        payload=client_payload,
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert client_response.response_status == 201

    client_key = client_response.response_json["client_key"]
    assert client_response.response_json["status"] == "PENDING"

    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )

    account_response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_created_account_response(account_response, client_key)


def test_create_account_for_active_company_returns_public_contract(
    api_database_engine: Engine,
) -> None:
    email = f"r04.company.account.{uuid4()}@example.com"
    client_payload = {
        "client_type": "COMPANY",
        "email": email,
        "cnpj": RandomGenerator.generate_cnpj(),
        "legal_name": "Empresa R04 Teste Ltda.",
        "trade_name": "Empresa R04",
        "timezone": "America/Sao_Paulo",
    }

    client_response = ClientRequisition.send(
        "POST",
        "/client",
        payload=client_payload,
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert client_response.response_status == 201

    client_key = client_response.response_json["client_key"]
    assert client_response.response_json["status"] == "PENDING"

    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="COMPANY",
    )

    account_response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_created_account_response(account_response, client_key)


def test_create_account_persists_account_and_initial_status_event(
    api_database_engine: Engine,
) -> None:
    email = f"r04.persistence.{uuid4()}@example.com"
    client_response = ClientRequisition.send(
        "POST",
        "/client",
        payload={
            "client_type": "INDIVIDUAL",
            "email": email,
            "cpf": RandomGenerator.generate_cpf(),
            "full_name": "Cliente R04 Persistencia",
            "birth_date": "1990-05-17",
            "timezone": "America/Sao_Paulo",
        },
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert client_response.response_status == 201

    client_key = client_response.response_json["client_key"]
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )

    account_response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_created_account_response(account_response, client_key)
    account_key = account_response.response_json["account_key"]

    with api_database_engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        accounts = connection.execute(
            text(
                """
                SELECT account.id, account.account_key::text AS account_key,
                       client.client_key::text AS client_key,
                       account.balance_cents,
                       status.enumerator AS status,
                       account.created_at, account.updated_at
                FROM account
                JOIN client ON client.id = account.client_id
                JOIN account_status AS status ON status.id = account.status_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).mappings().all()

        assert len(accounts) == 1
        account = accounts[0]
        assert account["account_key"] == account_key
        assert account["client_key"] == client_key
        assert account["status"] == "ACTIVE"
        assert type(account["balance_cents"]) is int
        assert account["balance_cents"] == 0
        for timestamp_name in ("created_at", "updated_at"):
            timestamp = account[timestamp_name]
            assert isinstance(timestamp, datetime)
            assert timestamp.tzinfo is not None
            assert timestamp.utcoffset() == timezone.utc.utcoffset(timestamp)

        events = connection.execute(
            text(
                """
                SELECT event.account_id, event.from_status_id,
                       destination.enumerator AS to_status,
                       event.actor_type, event.reason, event.created_at
                FROM account_status_event AS event
                JOIN account_status AS destination
                  ON destination.id = event.to_status_id
                WHERE event.account_id = :account_id
                """
            ),
            {"account_id": account["id"]},
        ).mappings().all()

    assert len(events) == 1
    event = events[0]
    assert event["account_id"] == account["id"]
    assert event["from_status_id"] is None
    assert event["to_status"] == "ACTIVE"
    assert event["actor_type"] == "SYSTEM"
    assert event["reason"] is None
    assert isinstance(event["created_at"], datetime)
    assert event["created_at"].tzinfo is not None
    assert event["created_at"].utcoffset() == timezone.utc.utcoffset(
        event["created_at"]
    )


def test_create_account_rejects_malformed_client_key() -> None:
    response = ClientRequisition.send(
        "POST",
        "/client/not-a-uuid/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_error_response(response, 400, INVALID_CLIENT_KEY_ERROR)


def test_create_account_rejects_unknown_client_key() -> None:
    client_key = str(uuid4())
    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_error_response(response, 404, _expected_client_not_found_error(client_key))


@pytest.mark.parametrize(
    ("headers", "case"),
    [
        (None, "missing"),
        ({"INTERNAL-TOKEN": "invalid-token"}, "invalid"),
    ],
)
def test_create_account_rejects_unauthenticated_requests_without_writes(
    api_database_engine: Engine,
    headers: dict[str, str] | None,
    case: str,
) -> None:
    client_key, email = _create_pending_individual()
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )

    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers=headers,
    )

    _assert_error_response(response, 403, FORBIDDEN_ERROR)
    assert _get_client_account_summary(api_database_engine, client_key) == {
        "status": "ACTIVE",
        "account_count": 0,
        "account_status": None,
        "account_event_count": 0,
        "client_event_count": 2,
    }


@pytest.mark.parametrize("client_key", ["not-a-uuid", str(uuid4())])
def test_authentication_precedes_client_key_validation(client_key: str) -> None:
    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": "invalid-token"},
    )

    _assert_error_response(response, 403, FORBIDDEN_ERROR)


@pytest.mark.parametrize(
    ("target_status", "expected_client_events"),
    [
        ("PENDING", 1),
        ("REJECTED", 2),
        ("INACTIVE", 3),
    ],
)
def test_create_account_rejects_non_active_client_without_persisting_account(
    api_database_engine: Engine,
    target_status: str,
    expected_client_events: int,
) -> None:
    client_key, email = _create_pending_individual()

    if target_status == "REJECTED":
        _transition_client_status(
            api_database_engine,
            client_key,
            email,
            "INDIVIDUAL",
            expected_status="PENDING",
            next_status="REJECTED",
            reason="Rejeição controlada do cenário R04",
        )
    elif target_status == "INACTIVE":
        _prepare_client_as_active(
            api_database_engine,
            client_key,
            email,
            expected_client_type="INDIVIDUAL",
        )
        _transition_client_status(
            api_database_engine,
            client_key,
            email,
            "INDIVIDUAL",
            expected_status="ACTIVE",
            next_status="INACTIVE",
            reason="Inativação controlada do cenário R04",
        )

    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_error_response(
        response,
        409,
        _expected_invalid_client_status_error(target_status),
    )
    assert _get_client_account_summary(api_database_engine, client_key) == {
        "status": target_status,
        "account_count": 0,
        "account_status": None,
        "account_event_count": 0,
        "client_event_count": expected_client_events,
    }


def test_create_account_rejects_second_request_without_duplicate_persistence(
    api_database_engine: Engine,
) -> None:
    client_key, email = _create_pending_individual()
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )
    first_response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_created_account_response(first_response, client_key)
    before_retry = _get_client_account_summary(api_database_engine, client_key)

    second_response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_error_response(second_response, 409, ACCOUNT_ALREADY_EXISTS_ERROR)
    assert _get_client_account_summary(api_database_engine, client_key) == before_retry
    assert before_retry == {
        "status": "ACTIVE",
        "account_count": 1,
        "account_status": "ACTIVE",
        "account_event_count": 1,
        "client_event_count": 2,
    }


def test_closed_account_remains_unique_for_the_client(
    api_database_engine: Engine,
) -> None:
    client_key, email = _create_pending_individual()
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )
    first_response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_created_account_response(first_response, client_key)
    _close_account_and_inactivate_client(api_database_engine, client_key)
    before_retry = _get_client_account_summary(api_database_engine, client_key)

    response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/account",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    # F01 valida ACTIVE antes da existência de ACCOUNT. O ciclo F02 de
    # fechamento torna o CLIENT INACTIVE, portanto CLI0002 tem precedência.
    _assert_error_response(
        response,
        409,
        _expected_invalid_client_status_error("INACTIVE"),
    )
    assert _get_client_account_summary(api_database_engine, client_key) == before_retry
    assert before_retry == {
        "status": "INACTIVE",
        "account_count": 1,
        "account_status": "CLOSED",
        "account_event_count": 2,
        "client_event_count": 3,
    }


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


def test_account_unique_violation_is_translated_to_conflict(
    api_database_engine: Engine,
) -> None:
    client_key, email = _create_pending_individual()
    _prepare_client_as_active(
        api_database_engine,
        client_key,
        email,
        expected_client_type="INDIVIDUAL",
    )

    with _raise_account_client_unique_violation_for_client(
        api_database_engine,
        client_key,
    ):
        response = ClientRequisition.send(
            "POST",
            f"/client/{client_key}/account",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

    _assert_error_response(response, 409, ACCOUNT_ALREADY_EXISTS_ERROR)
    assert _get_client_account_summary(api_database_engine, client_key) == {
        "status": "ACTIVE",
        "account_count": 0,
        "account_status": None,
        "account_event_count": 0,
        "client_event_count": 2,
    }
