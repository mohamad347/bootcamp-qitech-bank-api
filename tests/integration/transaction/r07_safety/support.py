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

__all__ = [name for name in globals() if not name.startswith("__")]
