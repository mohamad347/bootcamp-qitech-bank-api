"""Idempotência sequencial e replay histórico da TRANSFER."""

from uuid import uuid4

from sqlalchemy.engine import Engine

from tests.integration.transaction.support import (
    create_account,
    read_transfer_state,
    send_transfer,
)
from tests.utils import INTERNAL_TOKEN
from tests.utils.requisition import ClientRequisition


def test_transfer_replays_original_transaction_without_new_movement(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=100_000,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    original_response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
    )
    replay_response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
    )
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    assert original_response.response_status == 201
    assert replay_response.response_status == 201
    assert replay_response.response_json == original_response.response_json
    assert replay_response.response_json["fee_cents"] == 250
    assert state["source"]["balance_cents"] == 49_750
    assert state["target"]["balance_cents"] == 50_000
    assert len(state["transactions"]) == 1
    assert len(state["entries"]) == 3


def test_transfer_rejects_same_key_for_different_intention(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=100_000,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    original_response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
        50_000,
    )
    conflict_response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
        60_000,
    )
    state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    assert original_response.response_status == 201
    assert conflict_response.response_status == 409
    assert conflict_response.response_json["code"] == "TRX0003"
    assert state["source"]["balance_cents"] == 49_750
    assert state["target"]["balance_cents"] == 50_000
    assert len(state["transactions"]) == 1
    assert len(state["entries"]) == 3


def test_transfer_replay_survives_real_r06_closure_but_new_operation_does_not(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=50_250,
    )
    target_key = create_account(api_database_engine)
    original_key = uuid4()

    original_response = send_transfer(
        source_key,
        target_key,
        original_key,
    )
    state_after_original = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        original_key,
    )
    assert original_response.response_status == 201
    assert state_after_original["source"]["balance_cents"] == 0
    assert state_after_original["target"]["balance_cents"] == 50_000

    close_response = ClientRequisition.send(
        "PATCH",
        f"/account/{source_key}",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        payload={
            "status": "CLOSED",
            "reason": "Encerramento após transferência R07",
        },
    )
    assert close_response.response_status == 200
    assert close_response.response_json == {
        "account_key": source_key,
        "status": "CLOSED",
    }

    replay_response = send_transfer(
        source_key,
        target_key,
        original_key,
    )
    state_after_replay = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        original_key,
    )

    assert replay_response.response_status == 201
    assert replay_response.response_json == original_response.response_json
    assert replay_response.response_json["fee_cents"] == 250
    assert state_after_replay["source"]["status"] == "CLOSED"
    assert state_after_replay["source"]["balance_cents"] == 0
    assert state_after_replay["target"]["balance_cents"] == 50_000
    assert len(state_after_replay["transactions"]) == 1
    assert len(state_after_replay["entries"]) == 3

    new_key = uuid4()
    new_response = send_transfer(
        source_key,
        target_key,
        new_key,
    )
    new_state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        new_key,
    )

    assert new_response.response_status == 409
    assert new_response.response_json["code"] == "ACC0005"
    assert new_state["source"]["status"] == "CLOSED"
    assert new_state["source"]["balance_cents"] == 0
    assert new_state["target"]["balance_cents"] == 50_000
    assert new_state["transactions"] == []
    assert new_state["entries"] == []
