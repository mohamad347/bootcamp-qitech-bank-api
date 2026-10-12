"""Seguran?a transacional da R07: cen?rios organizados por comportamento."""

from .support import *


def test_transfer_rolls_back_all_effects_and_does_not_consume_key(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=100_000,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    with _reject_transaction_entry(
        api_database_engine,
        idempotency_key,
        entry_type="FEE",
    ):
        failed_response = send_transfer(
            source_key,
            target_key,
            idempotency_key,
        )

    failed_state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    assert failed_response.response_status == 500
    assert failed_response.response_json["code"] == "QIT000500"
    assert failed_state["source"]["balance_cents"] == 100_000
    assert failed_state["target"]["balance_cents"] == 0
    assert failed_state["transactions"] == []
    assert failed_state["entries"] == []
    assert _count_entries_for_accounts(
        api_database_engine,
        source_key,
        target_key,
    ) == 0

    retry_response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
    )
    retry_state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    assert retry_response.response_status == 201
    assert retry_state["source"]["balance_cents"] == 49_750
    assert retry_state["target"]["balance_cents"] == 50_000
    assert len(retry_state["transactions"]) == 1
    assert len(retry_state["entries"]) == 3
    assert retry_state["transactions"][0]["request_control_key"] == (
        idempotency_key
    )
    assert str(retry_state["transactions"][0]["transaction_key"]) == (
        retry_response.response_json["transaction_key"]
    )
    assert [
        (
            str(entry["account_key"]),
            entry["direction"],
            entry["entry_type"],
            entry["amount_cents"],
            entry["balance_after_cents"],
        )
        for entry in retry_state["entries"]
    ] == [
        (source_key, "DEBIT", "PRINCIPAL", 50_000, 50_000),
        (source_key, "DEBIT", "FEE", 250, 49_750),
        (target_key, "CREDIT", "PRINCIPAL", 50_000, 50_000),
    ]


def test_deferred_commit_failure_rolls_back_balances_and_all_writes(
    api_database_engine: Engine,
) -> None:
    source_key = create_account(
        api_database_engine,
        balance_cents=100_000,
    )
    target_key = create_account(api_database_engine)
    idempotency_key = uuid4()
    initial_state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    with _reject_transaction_at_commit(
        api_database_engine,
        idempotency_key,
    ) as temporary_objects:
        failed_response = send_transfer(
            source_key,
            target_key,
            idempotency_key,
        )

    failed_state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    assert failed_response.response_status == 500
    assert failed_response.response_json["code"] == "QIT000500"
    assert failed_state["source"]["balance_cents"] == 100_000
    assert failed_state["target"]["balance_cents"] == 0
    assert failed_state["source"]["updated_at"] == initial_state["source"][
        "updated_at"
    ]
    assert failed_state["target"]["updated_at"] == initial_state["target"][
        "updated_at"
    ]
    assert failed_state["transactions"] == []
    assert failed_state["entries"] == []
    assert _count_entries_for_accounts(
        api_database_engine,
        source_key,
        target_key,
    ) == 0
    assert _count_temporary_objects(
        api_database_engine,
        *temporary_objects,
    ) == 0

    retry_response = send_transfer(
        source_key,
        target_key,
        idempotency_key,
    )
    retry_state = read_transfer_state(
        api_database_engine,
        source_key,
        target_key,
        idempotency_key,
    )

    assert retry_response.response_status == 201
    assert retry_state["source"]["balance_cents"] == 49_750
    assert retry_state["target"]["balance_cents"] == 50_000
    assert len(retry_state["transactions"]) == 1
    assert len(retry_state["entries"]) == 3
    assert retry_state["transactions"][0]["request_control_key"] == (
        idempotency_key
    )


def test_deposit_rolls_back_and_allows_retry_with_the_same_key(
    api_database_engine: Engine,
) -> None:
    account_key = create_account(api_database_engine)
    idempotency_key = uuid4()

    with _reject_transaction_entry(
        api_database_engine,
        idempotency_key,
        entry_type="PRINCIPAL",
    ):
        failed_response = send_deposit(account_key, idempotency_key)

    failed_state = read_deposit_state(
        api_database_engine,
        account_key,
        idempotency_key,
    )

    assert failed_response.response_status == 500
    assert failed_response.response_json["code"] == "QIT000500"
    assert failed_state["balance_cents"] == 0
    assert failed_state["transactions"] == []
    assert failed_state["entries"] == []
    assert _count_entries_for_accounts(api_database_engine, account_key) == 0

    retry_response = send_deposit(account_key, idempotency_key)
    retry_state = read_deposit_state(
        api_database_engine,
        account_key,
        idempotency_key,
    )

    assert retry_response.response_status == 201
    assert retry_state["balance_cents"] == 50_000
    assert len(retry_state["transactions"]) == 1
    assert len(retry_state["entries"]) == 1
    assert retry_state["transactions"][0]["request_control_key"] == (
        idempotency_key
    )
    assert str(retry_state["transactions"][0]["transaction_key"]) == (
        retry_response.response_json["transaction_key"]
    )
