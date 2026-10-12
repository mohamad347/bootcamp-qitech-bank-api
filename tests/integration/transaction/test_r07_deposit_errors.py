from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine

from tests.integration.transaction.support import (
    create_account,
    read_deposit_state,
    read_request_state,
    send_deposit,
    set_account_status,
)


BIGINT_MAX = 9_223_372_036_854_775_807


@pytest.mark.parametrize("invalid_amount", [0, -1])
def test_deposit_rejects_amount_below_minimum(
    active_account_key: str,
    api_database_engine: Engine,
    invalid_amount: int,
) -> None:
    idempotency_key = uuid4()

    response = send_deposit(
        active_account_key,
        idempotency_key,
        invalid_amount,
    )
    state = read_deposit_state(
        api_database_engine,
        active_account_key,
        idempotency_key,
    )

    assert response.response_status == 422
    assert response.response_json["code"] == "TRX0004"
    assert state["balance_cents"] == 0
    assert state["transactions"] == []
    assert state["entries"] == []


def test_deposit_rejects_amount_above_bigint(
    active_account_key: str,
    api_database_engine: Engine,
) -> None:
    idempotency_key = uuid4()

    response = send_deposit(
        active_account_key,
        idempotency_key,
        BIGINT_MAX + 1,
    )
    state = read_deposit_state(
        api_database_engine,
        active_account_key,
        idempotency_key,
    )

    assert response.response_status == 422
    assert response.response_json["code"] == "TRX0004"
    assert state["balance_cents"] == 0
    assert state["transactions"] == []
    assert state["entries"] == []


def test_deposit_rejects_balance_overflow(
    api_database_engine: Engine,
) -> None:
    initial_balance = BIGINT_MAX - 10
    account_key = create_account(
        api_database_engine,
        balance_cents=initial_balance,
    )
    idempotency_key = uuid4()

    response = send_deposit(account_key, idempotency_key, 11)
    state = read_deposit_state(
        api_database_engine,
        account_key,
        idempotency_key,
    )

    assert response.response_status == 422
    assert response.response_json["code"] == "TRX0004"
    assert state["balance_cents"] == initial_balance
    assert state["transactions"] == []
    assert state["entries"] == []


def test_deposit_returns_account_not_found_without_persisting(
    api_database_engine: Engine,
) -> None:
    missing_account_key = str(uuid4())
    idempotency_key = uuid4()

    response = send_deposit(missing_account_key, idempotency_key)
    state = read_request_state(api_database_engine, idempotency_key)

    assert response.response_status == 404
    assert response.response_json["code"] == "ACC0001"
    assert state["transactions"] == []
    assert state["entries"] == []


@pytest.mark.parametrize("account_status", ["INACTIVE", "CLOSED"])
def test_deposit_rejects_new_operation_for_non_active_account(
    api_database_engine: Engine,
    account_status: str,
) -> None:
    account_key = create_account(
        api_database_engine,
        status=account_status,
    )
    idempotency_key = uuid4()

    response = send_deposit(account_key, idempotency_key)
    state = read_deposit_state(
        api_database_engine,
        account_key,
        idempotency_key,
    )

    assert response.response_status == 409
    assert response.response_json["code"] == "ACC0005"
    assert state["balance_cents"] == 0
    assert state["status"] == account_status
    assert state["transactions"] == []
    assert state["entries"] == []


def test_failed_deposit_does_not_consume_idempotency_key(
    api_database_engine: Engine,
) -> None:
    account_key = create_account(api_database_engine, status="INACTIVE")
    idempotency_key = uuid4()

    rejected_response = send_deposit(account_key, idempotency_key)
    state_after_rejection = read_deposit_state(
        api_database_engine,
        account_key,
        idempotency_key,
    )
    assert rejected_response.response_status == 409
    assert rejected_response.response_json["code"] == "ACC0005"
    assert state_after_rejection["transactions"] == []
    assert state_after_rejection["entries"] == []

    set_account_status(api_database_engine, account_key, "ACTIVE")
    accepted_response = send_deposit(account_key, idempotency_key)
    final_state = read_deposit_state(
        api_database_engine,
        account_key,
        idempotency_key,
    )

    assert accepted_response.response_status == 201
    assert final_state["balance_cents"] == 50_000
    assert len(final_state["transactions"]) == 1
    assert len(final_state["entries"]) == 1
