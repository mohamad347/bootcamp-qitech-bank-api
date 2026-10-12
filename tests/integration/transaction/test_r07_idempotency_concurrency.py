"""Contrato público da Idempotency-Key sob requests concorrentes."""

from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from os import environ
from threading import Barrier
from time import monotonic, sleep
from uuid import UUID, uuid4

from requests import Response, Session
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from tests.integration.transaction.support import (
    create_account,
    read_deposit_state,
    read_request_state,
)
from tests.utils import INTERNAL_TOKEN


HTTP_TIMEOUT_SECONDS = 8
FUTURE_TIMEOUT_SECONDS = 10
GATE_TIMEOUT_SECONDS = 5


def _post_deposit(
    barrier: Barrier,
    account_key: str,
    idempotency_key: UUID,
    amount_cents: int,
) -> Response:
    barrier.wait(timeout=GATE_TIMEOUT_SECONDS)
    api_host = environ.get("SERVER_LOCALHOST", "0.0.0.0")
    api_port = environ.get("API_PORT", "3000")
    with Session() as http_session:
        return http_session.post(
            f"http://{api_host}:{api_port}/account/{account_key}/transaction",
            headers={
                "INTERNAL-TOKEN": INTERNAL_TOKEN,
                "Idempotency-Key": str(idempotency_key),
            },
            json={
                "transaction_type": "DEPOSIT",
                "amount_cents": amount_cents,
            },
            timeout=HTTP_TIMEOUT_SECONDS,
        )


def _wait_for_blocked_requests(
    connection: Connection,
    expected_count: int,
) -> None:
    blocker_pid = connection.execute(
        text("SELECT pg_backend_pid()")
    ).scalar_one()
    deadline = monotonic() + GATE_TIMEOUT_SECONDS
    while monotonic() < deadline:
        connection.execute(text("SELECT pg_stat_clear_snapshot()"))
        waiting_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM pg_stat_activity AS activity
                WHERE activity.datname = current_database()
                  AND activity.pid <> :blocker_pid
                  AND activity.wait_event_type = 'Lock'
                  AND activity.query ILIKE '%FOR UPDATE OF account%'
                """
            ),
            {"blocker_pid": blocker_pid},
        ).scalar_one()
        if waiting_count >= expected_count:
            return
        sleep(0.01)
    raise AssertionError(
        f"Expected {expected_count} requests blocked by backend "
        f"{blocker_pid}, observed fewer before timeout"
    )


def _run_gated_deposits(
    engine: Engine,
    requests_data: list[tuple[str, UUID, int]],
) -> list[Response]:
    barrier = Barrier(len(requests_data) + 1)
    first_account_key = requests_data[0][0]
    second_account_key = requests_data[1][0]

    with engine.connect() as lock_connection:
        gate_transaction = lock_connection.begin()
        locked_ids = lock_connection.execute(
            text(
                """
                SELECT id
                FROM account
                WHERE account_key IN (
                    CAST(:first_account_key AS uuid),
                    CAST(:second_account_key AS uuid)
                )
                ORDER BY id
                FOR UPDATE
                """
            ),
            {
                "first_account_key": first_account_key,
                "second_account_key": second_account_key,
            },
        ).scalars().all()
        assert len(locked_ids) == len(
            {first_account_key, second_account_key}
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    _post_deposit,
                    barrier,
                    account_key,
                    idempotency_key,
                    amount_cents,
                )
                for account_key, idempotency_key, amount_cents in requests_data
            ]
            try:
                barrier.wait(timeout=GATE_TIMEOUT_SECONDS)
                _wait_for_blocked_requests(
                    lock_connection,
                    expected_count=len(requests_data),
                )
            finally:
                if gate_transaction.is_active:
                    gate_transaction.rollback()

            return [
                future.result(timeout=FUTURE_TIMEOUT_SECONDS)
                for future in futures
            ]


def _response_summary(response: Response) -> dict:
    try:
        body = response.json()
    except ValueError:
        body = response.text
    return {"status": response.status_code, "body": body}


def test_concurrent_same_key_and_hash_replays_single_deposit(
    api_database_engine: Engine,
) -> None:
    account_key = create_account(api_database_engine)
    idempotency_key = uuid4()
    requests_data = [
        (account_key, idempotency_key, 50_000),
        (account_key, idempotency_key, 50_000),
    ]

    responses = _run_gated_deposits(api_database_engine, requests_data)
    state = read_deposit_state(
        api_database_engine,
        account_key,
        idempotency_key,
    )
    summaries = [_response_summary(response) for response in responses]

    assert state["balance_cents"] == 50_000
    assert len(state["transactions"]) == 1
    assert len(state["entries"]) == 1
    assert [response.status_code for response in responses] == [201, 201], (
        {
            "responses": summaries,
            "balance_cents": state["balance_cents"],
            "transaction_key": str(
                state["transactions"][0]["transaction_key"]
            ),
            "transaction_count": len(state["transactions"]),
            "entry_count": len(state["entries"]),
        }
    )
    assert responses[0].json() == responses[1].json()
    assert (
        responses[0].json()["transaction_key"]
        == responses[1].json()["transaction_key"]
    )


def test_concurrent_same_key_and_different_hash_returns_conflict(
    api_database_engine: Engine,
) -> None:
    account_a_key = create_account(api_database_engine)
    account_b_key = create_account(api_database_engine)
    assert account_a_key != account_b_key
    idempotency_key = uuid4()
    requests_data = [
        (account_a_key, idempotency_key, 50_000),
        (account_b_key, idempotency_key, 70_000),
    ]

    responses = _run_gated_deposits(api_database_engine, requests_data)
    request_state = read_request_state(
        api_database_engine,
        idempotency_key,
    )
    with api_database_engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        account_rows = connection.execute(
            text(
                """
                SELECT account_key, balance_cents
                FROM account
                WHERE account_key IN (
                    CAST(:account_a_key AS uuid),
                    CAST(:account_b_key AS uuid)
                )
                """
            ),
            {
                "account_a_key": account_a_key,
                "account_b_key": account_b_key,
            },
        ).mappings().all()
    balances = {
        str(account["account_key"]): account["balance_cents"]
        for account in account_rows
    }
    expected_hashes = {
        sha256(
            f"DEPOSIT|{account_a_key}|50000".encode("utf-8")
        ).hexdigest(),
        sha256(
            f"DEPOSIT|{account_b_key}|70000".encode("utf-8")
        ).hexdigest(),
    }
    summaries = [_response_summary(response) for response in responses]

    assert len(request_state["transactions"]) == 1
    assert len(request_state["entries"]) == 1
    assert request_state["transactions"][0]["request_hash"] in expected_hashes
    assert sorted(balances.values()) in ([0, 50_000], [0, 70_000])
    assert sorted(response.status_code for response in responses) == [201, 409], (
        {
            "responses": summaries,
            "balances": balances,
            "transaction_key": str(
                request_state["transactions"][0]["transaction_key"]
            ),
            "request_hash": request_state["transactions"][0][
                "request_hash"
            ],
            "transaction_count": len(request_state["transactions"]),
            "entry_count": len(request_state["entries"]),
        }
    )
    conflict_response = next(
        response for response in responses if response.status_code == 409
    )
    assert conflict_response.json()["code"] == "TRX0003"
