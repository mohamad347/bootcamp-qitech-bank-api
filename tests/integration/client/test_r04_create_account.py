"""Happy path inicial de abertura de conta para um CLIENT ACTIVE."""

from collections.abc import Iterator
from datetime import datetime, timezone
from os import environ
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url

from tests.utils import DbUtils, INTERNAL_TOKEN, RandomGenerator
from tests.utils.requisition import ClientRequisition


ACCOUNT_RESPONSE_FIELDS = {"account_key", "status", "balance_cents"}


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
