"""Atomicidade e invariantes finais das transações da R07."""

from collections.abc import Iterator
from contextlib import contextmanager
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.integration.transaction.support import (
    create_account,
    read_deposit_state,
    read_transfer_state,
    send_deposit,
    send_transfer,
)


@contextmanager
def _reject_transaction_entry(
    engine: Engine,
    idempotency_key: UUID,
    entry_type: str,
) -> Iterator[None]:
    """Falha uma entry da operação indicada e sempre remove o trigger."""
    assert entry_type in {"PRINCIPAL", "FEE"}
    suffix = uuid4().hex
    function_name = f"r07_fail_entry_function_{suffix}"
    trigger_name = f"r07_fail_entry_trigger_{suffix}"

    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF NEW.entry_type = '{entry_type}' AND EXISTS (
                    SELECT 1
                    FROM financial_transaction
                    WHERE id = NEW.transaction_id
                      AND request_control_key = '{idempotency_key}'::uuid
                ) THEN
                    RAISE EXCEPTION 'R07 controlled transaction entry failure';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON transaction_entry
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} "
                "ON transaction_entry"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )


@contextmanager
def _reject_transaction_at_commit(
    engine: Engine,
    idempotency_key: UUID,
) -> Iterator[tuple[str, str]]:
    """Falha no COMMIT após todas as escritas financeiras serem processadas."""
    suffix = uuid4().hex
    function_name = f"r07_fail_commit_function_{suffix}"
    trigger_name = f"r07_fail_commit_trigger_{suffix}"

    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM financial_transaction
                    WHERE id = NEW.transaction_id
                      AND request_control_key = '{idempotency_key}'::uuid
                ) THEN
                    RAISE EXCEPTION 'R07 controlled deferred commit failure';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE CONSTRAINT TRIGGER {trigger_name}
            AFTER INSERT ON transaction_entry
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        yield trigger_name, function_name
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} "
                "ON transaction_entry"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )


def _count_temporary_objects(
    engine: Engine,
    trigger_name: str,
    function_name: str,
) -> int:
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        return connection.execute(
            text(
                """
                SELECT
                    (SELECT COUNT(1) FROM pg_trigger
                     WHERE tgname = :trigger_name)
                    +
                    (SELECT COUNT(1) FROM pg_proc
                     WHERE proname = :function_name)
                """
            ),
            {
                "trigger_name": trigger_name,
                "function_name": function_name,
            },
        ).scalar_one()


def _count_entries_for_accounts(
    engine: Engine,
    *account_keys: str,
) -> int:
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        return connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM transaction_entry AS entry
                JOIN account ON account.id = entry.account_id
                WHERE account.account_key = ANY(:account_keys)
                """
            ),
            {"account_keys": [UUID(key) for key in account_keys]},
        ).scalar_one()


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


def test_sequential_deposits_record_each_historical_balance(
    api_database_engine: Engine,
) -> None:
    account_key = create_account(api_database_engine)
    first_key = uuid4()
    second_key = uuid4()

    first_response = send_deposit(account_key, first_key, amount_cents=50_000)
    second_response = send_deposit(account_key, second_key, amount_cents=20_000)

    assert first_response.response_status == 201
    assert second_response.response_status == 201

    with api_database_engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        account_balance = connection.execute(
            text(
                """
                SELECT balance_cents
                FROM account
                WHERE account_key = :account_key
                """
            ),
            {"account_key": UUID(account_key)},
        ).scalar_one()
        entries = connection.execute(
            text(
                """
                SELECT transaction.request_control_key,
                       entry.direction, entry.entry_type,
                       entry.amount_cents, entry.balance_after_cents
                FROM transaction_entry AS entry
                JOIN financial_transaction AS transaction
                  ON transaction.id = entry.transaction_id
                WHERE transaction.request_control_key IN (
                    :first_key,
                    :second_key
                )
                ORDER BY entry.id
                """
            ),
            {"first_key": first_key, "second_key": second_key},
        ).mappings().all()

    assert account_balance == 70_000
    assert [
        (
            entry["request_control_key"],
            entry["direction"],
            entry["entry_type"],
            entry["amount_cents"],
            entry["balance_after_cents"],
        )
        for entry in entries
    ] == [
        (first_key, "CREDIT", "PRINCIPAL", 50_000, 50_000),
        (second_key, "CREDIT", "PRINCIPAL", 20_000, 70_000),
    ]
    assert entries[-1]["balance_after_cents"] == account_balance
