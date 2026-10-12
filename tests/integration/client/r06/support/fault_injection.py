"""Helpers coesos e locais da rota R06."""

from .base import *


@contextmanager
def _reject_status_event_for_account(
    engine: Engine,
    account_key: str,
    event_table: str,
) -> Iterator[None]:
    assert event_table in {"account_status_event", "client_status_event"}
    suffix = uuid4().hex
    function_name = f"r06_fail_event_function_{suffix}"
    trigger_name = f"r06_fail_event_trigger_{suffix}"
    with engine.begin() as connection:
        owner = connection.execute(
            text(
                """
                SELECT account.id AS account_id, account.client_id
                FROM account
                WHERE account.account_key = CAST(:account_key AS uuid)
                """
            ),
            {"account_key": account_key},
        ).mappings().one()
        owner_column = "account_id" if event_table == "account_status_event" else "client_id"
        owner_id = owner[owner_column]
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF NEW.{owner_column} = {owner_id} THEN
                    RAISE EXCEPTION 'R06 controlled event failure';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON {event_table}
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON {event_table}"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )

__all__ = [name for name in globals() if not name.startswith("__")]
