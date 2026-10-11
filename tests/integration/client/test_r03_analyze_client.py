"""Integração da R03 entre API, Analysis Provider e PostgreSQL."""

import json
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from os import environ
from threading import Barrier
from typing import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.engine import Engine

from tests.utils import DbUtils, INTERNAL_TOKEN, RandomGenerator
from tests.utils.mockserver import MockServer
from tests.utils.requisition import BaseConnectorResponse, ClientRequisition


ANALYSIS_PROVIDER_TIMEOUT_SECONDS = int(
    environ.get("ANALYSIS_PROVIDER_TIMEOUT", "5")
)
CONCURRENT_PROVIDER_DELAY_MILLISECONDS = 1_000


@pytest.fixture(scope="module")
def app_db_engine() -> Iterator[Engine]:
    """Abre conexões de leitura no mesmo banco usado pela API."""
    app_url = make_url(DbUtils.database_url())
    test_database_url = environ.get("TEST_DATABASE_URL")

    if app_url.database != "bootcamp" or app_url.database.endswith("_test"):
        pytest.fail("A verificação da R03 deve consultar o banco bootcamp da API.")
    if test_database_url and app_url == make_url(test_database_url):
        pytest.fail("O banco da API não pode ser TEST_DATABASE_URL.")

    engine = create_engine(app_url)
    try:
        yield engine
    finally:
        engine.dispose()


def _provider_request(
    client_key: str,
    client_type: str,
    document: str,
) -> dict:
    return {
        "method": "POST",
        "path": "/v1/client-analysis",
        "body": {
            "type": "JSON",
            "json": {
                "client_key": client_key,
                "client_type": client_type,
                "document": document,
            },
            "matchType": "STRICT",
        },
    }


def _expect_provider_response(
    expected_request: dict,
    response_body: dict | str,
    status_code: int = 200,
    delay_milliseconds: int | None = None,
) -> None:
    serialized_body = (
        json.dumps(response_body)
        if isinstance(response_body, dict)
        else response_body
    )
    http_response = {
        "statusCode": status_code,
        "headers": {"Content-Type": ["application/json"]},
        "body": serialized_body,
    }
    if delay_milliseconds is not None:
        http_response["delay"] = {
            "timeUnit": "MILLISECONDS",
            "value": delay_milliseconds,
        }

    MockServer.expect(
        http_request=expected_request,
        http_response=http_response,
    )


def _expect_client_analysis(
    expected_request: dict,
    decision: str,
    reason: str | None,
) -> None:
    _expect_provider_response(
        expected_request,
        {"decision": decision, "reason": reason},
    )


def _analyze_client(client_key: str) -> BaseConnectorResponse:
    return ClientRequisition.send(
        "POST",
        f"/client/{client_key}/analysis",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )


def _verify_provider_was_not_called() -> None:
    MockServer.verify_exactly(
        {
            "method": "POST",
            "path": "/v1/client-analysis",
        },
        count=0,
    )


def _assert_client_remains_pending(
    app_db_engine: Engine,
    client_key: str,
) -> None:
    with app_db_engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        persisted = connection.execute(
            text("""
                SELECT status.enumerator AS status,
                       COUNT(event.id) AS event_count
                FROM client AS client
                JOIN client_status AS status ON status.id = client.status_id
                LEFT JOIN client_status_event AS event
                  ON event.client_id = client.id
                WHERE client.client_key = CAST(:client_key AS uuid)
                GROUP BY status.enumerator
            """),
            {"client_key": client_key},
        ).mappings().one()

    assert dict(persisted) == {
        "status": "PENDING",
        "event_count": 1,
    }


def _create_pending_individual() -> tuple[str, str]:
    cpf = RandomGenerator.generate_cpf()
    response = ClientRequisition.send(
        "POST",
        "/client",
        payload={
            "client_type": "INDIVIDUAL",
            "email": f"r03.client.{uuid4()}@example.com",
            "cpf": cpf,
            "full_name": "Cliente R03",
            "birth_date": "2000-01-01",
            "timezone": "America/Sao_Paulo",
        },
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert response.response_status == 201

    normalized_cpf = cpf.replace(".", "").replace("-", "")
    return response.response_json["client_key"], normalized_cpf


def _create_pending_company() -> tuple[str, str]:
    cnpj = RandomGenerator.generate_cnpj()
    response = ClientRequisition.send(
        "POST",
        "/client",
        payload={
            "client_type": "COMPANY",
            "email": f"r03.company.{uuid4()}@example.com",
            "cnpj": cnpj,
            "legal_name": "Cliente R03 Ltda",
            "trade_name": "Cliente R03",
            "timezone": "America/Sao_Paulo",
        },
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert response.response_status == 201

    normalized_cnpj = (
        cnpj.replace(".", "").replace("/", "").replace("-", "")
    )
    return response.response_json["client_key"], normalized_cnpj


def _prepare_client_status(
    app_db_engine: Engine,
    client_key: str,
    status: str,
) -> None:
    """Prepara o estado e seu histórico quando não há rota pública para isso."""
    status_path = ["ACTIVE", "INACTIVE"] if status == "INACTIVE" else [status]

    with app_db_engine.begin() as connection:
        client = connection.execute(
            text("""
                SELECT client.id, client.status_id
                FROM client
                WHERE client_key = CAST(:client_key AS uuid)
            """),
            {"client_key": client_key},
        ).mappings().one()

        current_status_id = client["status_id"]
        for next_status in status_path:
            next_status_id = connection.execute(
                text("""
                    SELECT id
                    FROM client_status
                    WHERE enumerator = :status
                """),
                {"status": next_status},
            ).scalar_one()
            connection.execute(
                text("""
                    INSERT INTO client_status_event (
                        client_id,
                        from_status_id,
                        to_status_id,
                        actor_type,
                        reason,
                        created_at
                    ) VALUES (
                        :client_id,
                        :from_status_id,
                        :to_status_id,
                        'INTERNAL',
                        'Preparação do cenário de teste',
                        NOW()
                    )
                """),
                {
                    "client_id": client["id"],
                    "from_status_id": current_status_id,
                    "to_status_id": next_status_id,
                },
            )
            current_status_id = next_status_id

        connection.execute(
            text("""
                UPDATE client
                SET status_id = :status_id,
                    updated_at = NOW()
                WHERE id = :client_id
            """),
            {
                "client_id": client["id"],
                "status_id": current_status_id,
            },
        )


def _get_client_status(app_db_engine: Engine, client_key: str) -> str:
    with app_db_engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        return connection.execute(
            text("""
                SELECT status.enumerator
                FROM client AS client
                JOIN client_status AS status ON status.id = client.status_id
                WHERE client.client_key = CAST(:client_key AS uuid)
            """),
            {"client_key": client_key},
        ).scalar_one()


def _get_client_lifecycle_summary(
    app_db_engine: Engine,
    client_key: str,
) -> dict:
    with app_db_engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        lifecycle = connection.execute(
            text("""
                SELECT status.enumerator AS status,
                       COUNT(event.id) AS event_count
                FROM client AS client
                JOIN client_status AS status ON status.id = client.status_id
                LEFT JOIN client_status_event AS event
                  ON event.client_id = client.id
                WHERE client.client_key = CAST(:client_key AS uuid)
                GROUP BY status.enumerator
            """),
            {"client_key": client_key},
        ).mappings().one()

    return dict(lifecycle)


@contextmanager
def _reject_next_status_event_for_client(
    app_db_engine: Engine,
    client_key: str,
) -> Iterator[None]:
    """Força erro no INSERT do evento e sempre remove o trigger de teste."""
    suffix = uuid4().hex
    function_name = f"r03_fail_event_function_{suffix}"
    trigger_name = f"r03_fail_event_trigger_{suffix}"

    with app_db_engine.begin() as connection:
        client_id = connection.execute(
            text("""
                SELECT id
                FROM client
                WHERE client_key = CAST(:client_key AS uuid)
            """),
            {"client_key": client_key},
        ).scalar_one()

        connection.exec_driver_sql(f"""
            CREATE FUNCTION {function_name}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.client_id = {client_id}
                   AND EXISTS (
                       SELECT 1
                       FROM client
                       JOIN client_status AS status
                         ON status.id = client.status_id
                       WHERE client.id = NEW.client_id
                         AND status.enumerator = 'ACTIVE'
                   ) THEN
                    RAISE EXCEPTION 'Falha controlada no evento da R03';
                END IF;
                RETURN NEW;
            END;
            $$
        """)
        connection.exec_driver_sql(f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON client_status_event
            FOR EACH ROW
            EXECUTE FUNCTION {function_name}()
        """)

    try:
        yield
    finally:
        with app_db_engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} "
                "ON client_status_event"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )


# Fluxos de sucesso e persistência


def test_approve_pending_client_updates_status_and_creates_event(
    app_db_engine: Engine,
) -> None:
    MockServer.reset()

    client_key, normalized_cpf = _create_pending_individual()
    expected_provider_request = _provider_request(
        client_key,
        "INDIVIDUAL",
        normalized_cpf,
    )
    _expect_client_analysis(
        expected_request=expected_provider_request,
        decision="APPROVE",
        reason=None,
    )

    analysis_response = _analyze_client(client_key)

    assert analysis_response.response_status == 200
    assert analysis_response.response_json == {
        "client_key": client_key,
        "status": "ACTIVE",
    }

    MockServer.verify_exactly(expected_provider_request, count=1)

    with app_db_engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        client = connection.execute(
            text("""
                SELECT c.id, current_status.enumerator AS status,
                       c.created_at, c.updated_at
                FROM client AS c
                JOIN client_status AS current_status
                  ON current_status.id = c.status_id
                WHERE c.client_key = CAST(:client_key AS uuid)
            """),
            {"client_key": client_key},
        ).mappings().one()

        events = connection.execute(
            text("""
                SELECT previous_status.enumerator AS from_status,
                       next_status.enumerator AS to_status,
                       event.actor_type, event.reason
                FROM client_status_event AS event
                LEFT JOIN client_status AS previous_status
                  ON previous_status.id = event.from_status_id
                JOIN client_status AS next_status
                  ON next_status.id = event.to_status_id
                WHERE event.client_id = :client_id
                ORDER BY event.created_at, event.id
            """),
            {"client_id": client["id"]},
        ).mappings().all()

    assert client["status"] == "ACTIVE"
    assert client["updated_at"] >= client["created_at"]
    assert [dict(event) for event in events] == [
        {
            "from_status": None,
            "to_status": "PENDING",
            "actor_type": "SYSTEM",
            "reason": None,
        },
        {
            "from_status": "PENDING",
            "to_status": "ACTIVE",
            "actor_type": "INTERNAL",
            "reason": None,
        },
    ]


def test_reject_pending_client_persists_reason_in_status_event(
    app_db_engine: Engine,
) -> None:
    MockServer.reset()

    client_key, normalized_cnpj = _create_pending_company()
    expected_provider_request = _provider_request(
        client_key,
        "COMPANY",
        normalized_cnpj,
    )
    provider_reason = "  Cadastro nao aprovado  "
    persisted_reason = "Cadastro nao aprovado"
    _expect_client_analysis(
        expected_request=expected_provider_request,
        decision="REJECT",
        reason=provider_reason,
    )

    analysis_response = _analyze_client(client_key)

    assert analysis_response.response_status == 200
    assert analysis_response.response_json == {
        "client_key": client_key,
        "status": "REJECTED",
    }
    MockServer.verify_exactly(expected_provider_request, count=1)

    with app_db_engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        lifecycle = connection.execute(
            text("""
                SELECT current_status.enumerator AS status,
                       previous_status.enumerator AS from_status,
                       next_status.enumerator AS to_status,
                       event.actor_type, event.reason
                FROM client AS client
                JOIN client_status AS current_status
                  ON current_status.id = client.status_id
                JOIN client_status_event AS event
                  ON event.client_id = client.id
                LEFT JOIN client_status AS previous_status
                  ON previous_status.id = event.from_status_id
                JOIN client_status AS next_status
                  ON next_status.id = event.to_status_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                  AND previous_status.enumerator = 'PENDING'
            """),
            {"client_key": client_key},
        ).mappings().one()

    assert dict(lifecycle) == {
        "status": "REJECTED",
        "from_status": "PENDING",
        "to_status": "REJECTED",
        "actor_type": "INTERNAL",
        "reason": persisted_reason,
    }


# Validação do contrato do Analysis Provider


@pytest.mark.parametrize(
    "provider_body",
    [
        {"reason": None},
        {"decision": "MAYBE", "reason": None},
        {"decision": "REJECT"},
        {"decision": "REJECT", "reason": None},
        {"decision": "REJECT", "reason": "   "},
        {"decision": "REJECT", "reason": "R" * 501},
    ],
    ids=[
        "missing-decision",
        "invalid-decision",
        "missing-reason",
        "null-reason",
        "blank-reason",
        "reason-too-long",
    ],
)
def test_invalid_provider_response_does_not_change_client(
    app_db_engine: Engine,
    provider_body: dict,
) -> None:
    MockServer.reset()

    client_key, normalized_cpf = _create_pending_individual()
    expected_provider_request = _provider_request(
        client_key,
        "INDIVIDUAL",
        normalized_cpf,
    )
    _expect_provider_response(expected_provider_request, provider_body)

    analysis_response = _analyze_client(client_key)

    assert analysis_response.response_status == 500
    assert analysis_response.response_json["code"] == "QIT000500"
    MockServer.verify_exactly(expected_provider_request, count=1)
    _assert_client_remains_pending(app_db_engine, client_key)


# Elegibilidade local: estes cenários não devem chamar o provider


@pytest.mark.parametrize(
    "current_status",
    ["ACTIVE", "REJECTED", "INACTIVE"],
)
def test_non_pending_client_returns_conflict_without_calling_provider(
    app_db_engine: Engine,
    current_status: str,
) -> None:
    client_key, _ = _create_pending_individual()
    _prepare_client_status(app_db_engine, client_key, current_status)
    MockServer.reset()

    response = _analyze_client(client_key)

    assert response.response_status == 409
    assert response.response_json["code"] == "CLI0002"
    _verify_provider_was_not_called()
    assert _get_client_status(app_db_engine, client_key) == current_status


def test_unknown_client_returns_not_found_without_calling_provider() -> None:
    MockServer.reset()
    unknown_client_key = str(uuid4())

    response = _analyze_client(unknown_client_key)

    assert response.response_status == 404
    assert response.response_json["code"] == "CLI0001"
    _verify_provider_was_not_called()


def test_malformed_client_key_returns_bad_request_without_calling_provider() -> None:
    MockServer.reset()

    response = _analyze_client("not-a-uuid")

    assert response.response_status == 400
    assert response.response_json["code"] == "QIT000010"
    _verify_provider_was_not_called()


def test_invalid_internal_token_does_not_call_provider() -> None:
    MockServer.reset()

    response = ClientRequisition.send(
        "POST",
        f"/client/{uuid4()}/analysis",
        headers={"INTERNAL-TOKEN": f"{INTERNAL_TOKEN}-invalid"},
    )

    assert response.response_status == 403
    assert response.response_json["code"] == "QIT000002"
    _verify_provider_was_not_called()


# Resiliência da integração externa


@pytest.mark.parametrize(
    ("provider_status", "provider_body"),
    [
        (500, {"error": "provider unavailable"}),
        (200, "this is not valid JSON"),
    ],
    ids=["provider-http-500", "provider-invalid-json"],
)
def test_provider_failure_does_not_change_client(
    app_db_engine: Engine,
    provider_status: int,
    provider_body: dict | str,
) -> None:
    MockServer.reset()
    client_key, normalized_cpf = _create_pending_individual()
    expected_provider_request = _provider_request(
        client_key,
        "INDIVIDUAL",
        normalized_cpf,
    )
    _expect_provider_response(
        expected_request=expected_provider_request,
        response_body=provider_body,
        status_code=provider_status,
    )

    response = _analyze_client(client_key)

    assert response.response_status == 500
    assert response.response_json["code"] == "QIT000500"
    MockServer.verify_exactly(expected_provider_request, count=1)
    _assert_client_remains_pending(app_db_engine, client_key)


def test_provider_timeout_does_not_change_client(
    app_db_engine: Engine,
) -> None:
    MockServer.reset()
    client_key, normalized_cpf = _create_pending_individual()
    expected_provider_request = _provider_request(
        client_key,
        "INDIVIDUAL",
        normalized_cpf,
    )
    _expect_provider_response(
        expected_request=expected_provider_request,
        response_body={"decision": "APPROVE", "reason": None},
        delay_milliseconds=(ANALYSIS_PROVIDER_TIMEOUT_SECONDS + 1) * 1_000,
    )

    response = _analyze_client(client_key)

    assert response.response_status == 500
    assert response.response_json["code"] == "QIT000500"
    MockServer.verify_exactly(expected_provider_request, count=1)
    _assert_client_remains_pending(app_db_engine, client_key)


# Concorrência e atomicidade no PostgreSQL


def test_concurrent_analysis_allows_only_one_status_transition(
    app_db_engine: Engine,
) -> None:
    MockServer.reset()
    client_key, normalized_cpf = _create_pending_individual()
    expected_provider_request = _provider_request(
        client_key,
        "INDIVIDUAL",
        normalized_cpf,
    )
    _expect_provider_response(
        expected_request=expected_provider_request,
        response_body={"decision": "APPROVE", "reason": None},
        delay_milliseconds=CONCURRENT_PROVIDER_DELAY_MILLISECONDS,
    )

    start_gate = Barrier(3)

    def send_analysis() -> BaseConnectorResponse:
        start_gate.wait(timeout=5)
        return _analyze_client(client_key)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(send_analysis) for _ in range(2)]
        start_gate.wait(timeout=5)
        responses = [future.result(timeout=15) for future in futures]

    assert sorted(response.response_status for response in responses) == [200, 409]

    successful_response = next(
        response for response in responses if response.response_status == 200
    )
    conflict_response = next(
        response for response in responses if response.response_status == 409
    )
    assert successful_response.response_json == {
        "client_key": client_key,
        "status": "ACTIVE",
    }
    assert conflict_response.response_json["code"] == "CLI0002"
    MockServer.verify_exactly(expected_provider_request, count=2)
    assert _get_client_lifecycle_summary(app_db_engine, client_key) == {
        "status": "ACTIVE",
        "event_count": 2,
    }


def test_event_failure_rolls_back_client_status_change(
    app_db_engine: Engine,
) -> None:
    MockServer.reset()
    client_key, normalized_cpf = _create_pending_individual()
    expected_provider_request = _provider_request(
        client_key,
        "INDIVIDUAL",
        normalized_cpf,
    )
    _expect_client_analysis(
        expected_request=expected_provider_request,
        decision="APPROVE",
        reason=None,
    )

    with _reject_next_status_event_for_client(app_db_engine, client_key):
        response = _analyze_client(client_key)

    assert response.response_status == 500
    assert response.response_json["code"] == "QIT000500"
    MockServer.verify_exactly(expected_provider_request, count=1)
    _assert_client_remains_pending(app_db_engine, client_key)
