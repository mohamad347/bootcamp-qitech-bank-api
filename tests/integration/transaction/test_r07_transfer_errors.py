"""Validações estruturais, de domínio e limites da TRANSFER."""

from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine

from tests.integration.transaction.support import (
    create_account,
    read_transfer_state,
    send_transfer,
)
from tests.utils import INTERNAL_TOKEN
from tests.utils.requisition import ClientRequisition


BIGINT_MAX = 9_223_372_036_854_775_807


def _assert_error(response, status: int, code: str) -> None:
    assert response.response_status == status
    assert response.response_json["code"] == code


@pytest.mark.parametrize(
    "payload",
    [
        {"transaction_type": "TRANSFER", "amount_cents": 50_000},
        {
            "transaction_type": "TRANSFER",
            "target_account_key": "not-a-uuid",
            "amount_cents": 50_000,
        },
        {
            "transaction_type": "TRANSFER",
            "target_account_key": str(uuid4()),
            "amount_cents": 50_000,
            "unexpected": True,
        },
    ],
    ids=["missing-target", "invalid-target", "extra-property"],
)
def test_transfer_rejects_structurally_invalid_body(
    active_account_key: str,
    payload: dict,
) -> None:
    response = ClientRequisition.send(
        "POST",
        f"/account/{active_account_key}/transaction",
        headers={
            "INTERNAL-TOKEN": INTERNAL_TOKEN,
            "Idempotency-Key": str(uuid4()),
        },
        payload=payload,
    )

    _assert_error(response, 400, "QIT000001")


@pytest.mark.parametrize("invalid_amount", [999, 0])
def test_transfer_rejects_amount_below_minimum(
    api_database_engine: Engine,
    invalid_amount: int,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=100_000,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
        invalid_amount,
    )
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    _assert_error(response, 422, "TRX0004")
    assert state["source"]["balance_cents"] == 100_000
    assert state["target"]["balance_cents"] == 0
    assert state["transactions"] == []
    assert state["entries"] == []


def test_transfer_rejects_self_transfer_without_consuming_key(
    api_database_engine: Engine,
) -> None:
    account_key = create_account(
        api_database_engine,
        balance_cents=100_000,
    )
    idempotency_key = uuid4()

    response = send_transfer(
        account_key,
        account_key,
        idempotency_key,
    )
    state = read_transfer_state(
        api_database_engine,
        account_key,
        account_key,
        idempotency_key,
    )

    _assert_error(response, 409, "TRX0002")
    assert state["source"]["balance_cents"] == 100_000
    assert state["transactions"] == []
    assert state["entries"] == []


def test_transfer_returns_source_account_not_found(
    api_database_engine: Engine,
) -> None:
    source_key = str(uuid4())
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    response = send_transfer(source_key, target_key, idempotency_key)
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    _assert_error(response, 404, "ACC0001")
    assert state["source"] is None
    assert state["target"]["balance_cents"] == 0
    assert state["transactions"] == []
    assert state["entries"] == []


def test_transfer_returns_target_account_not_found(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=100_000,
    )
    target_key = str(uuid4())
    idempotency_key = uuid4()

    response = send_transfer(source_key, target_key, idempotency_key)
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    _assert_error(response, 404, "ACC0001")
    assert state["source"]["balance_cents"] == 100_000
    assert state["target"] is None
    assert state["transactions"] == []
    assert state["entries"] == []


@pytest.mark.parametrize("status", ["INACTIVE", "CLOSED"])
def test_transfer_rejects_non_active_source(
    api_database_engine: Engine,
    status: str,
) -> None:
    initial_balance = 100_000 if status == "INACTIVE" else 0
    source_key = create_account(
        api_database_engine,
        status=status,
        balance_cents=initial_balance,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    response = send_transfer(source_key, target_key, idempotency_key)
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    _assert_error(response, 409, "ACC0005")
    assert state["source"]["balance_cents"] == initial_balance
    assert state["target"]["balance_cents"] == 0
    assert state["transactions"] == []
    assert state["entries"] == []


@pytest.mark.parametrize("status", ["INACTIVE", "CLOSED"])
def test_transfer_rejects_non_active_target(
    api_database_engine: Engine,
    status: str,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=100_000,
    )
    target_key = create_account(api_database_engine, status=status)
    idempotency_key = uuid4()

    response = send_transfer(source_key, target_key, idempotency_key)
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    _assert_error(response, 409, "ACC0005")
    assert state["source"]["balance_cents"] == 100_000
    assert state["target"]["balance_cents"] == 0
    assert state["transactions"] == []
    assert state["entries"] == []


def test_transfer_rejects_insufficient_balance(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=50_249,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    response = send_transfer(source_key, target_key, idempotency_key)
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    _assert_error(response, 422, "TRX0001")
    assert state["source"]["balance_cents"] == 50_249
    assert state["target"]["balance_cents"] == 0
    assert state["transactions"] == []
    assert state["entries"] == []


def test_transfer_accepts_exact_amount_plus_fee_balance(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=50_250,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    response = send_transfer(source_key, target_key, idempotency_key)
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    assert response.response_status == 201
    assert response.response_json["fee_cents"] == 250
    assert state["source"]["balance_cents"] == 0
    assert state["target"]["balance_cents"] == 50_000
    assert len(state["transactions"]) == 1
    assert len(state["entries"]) == 3


def test_transfer_rejects_amount_above_bigint(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=100_000,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
        BIGINT_MAX + 1,
    )
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    _assert_error(response, 422, "TRX0004")
    assert state["source"]["balance_cents"] == 100_000
    assert state["target"]["balance_cents"] == 0
    assert state["transactions"] == []
    assert state["entries"] == []


def test_transfer_rejects_amount_plus_fee_above_bigint(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=BIGINT_MAX,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
        BIGINT_MAX,
    )
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    _assert_error(response, 422, "TRX0004")
    assert state["source"]["balance_cents"] == BIGINT_MAX
    assert state["target"]["balance_cents"] == 0
    assert state["transactions"] == []
    assert state["entries"] == []


def test_transfer_rejects_target_balance_overflow(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=2_000,
    )
    target_key = create_account(
        api_database_engine,
        balance_cents=BIGINT_MAX - 500,
    )
    idempotency_key = uuid4()

    response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
        1_000,
    )
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    _assert_error(response, 422, "TRX0004")
    assert state["source"]["balance_cents"] == 2_000
    assert state["target"]["balance_cents"] == BIGINT_MAX - 500
    assert state["transactions"] == []
    assert state["entries"] == []
