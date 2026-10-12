"""Helpers coesos e locais da rota R04."""

from .base import *


@contextmanager
def _reject_account_initial_event_for_client(
    engine: Engine,
    client_key: str,
) -> Iterator[None]:
    """Injeta uma falha temporária e localizada antes do evento de ACCOUNT."""
    suffix = uuid4().hex
    function_name = f"r04_fail_account_event_function_{suffix}"
    trigger_name = f"r04_fail_account_event_trigger_{suffix}"

    with engine.begin() as connection:
        client_id = connection.execute(
            text(
                """
                SELECT id
                FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM account
                    WHERE id = NEW.account_id AND client_id = {client_id}
                ) THEN
                    RAISE EXCEPTION 'Falha controlada no evento da R04';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON account_status_event
            FOR EACH ROW
            EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON account_status_event"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )


@contextmanager
def _raise_account_client_unique_violation_for_client(
    engine: Engine,
    client_key: str,
) -> Iterator[None]:
    """Simula somente a UniqueViolation final de ACCOUNT.client_id."""
    suffix = uuid4().hex
    function_name = f"r04_unique_account_function_{suffix}"
    trigger_name = f"r04_unique_account_trigger_{suffix}"

    with engine.begin() as connection:
        client_id = connection.execute(
            text(
                """
                SELECT id
                FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                IF NEW.client_id = {client_id} THEN
                    RAISE EXCEPTION USING
                        ERRCODE = '23505',
                        CONSTRAINT = 'account_client_id_key',
                        MESSAGE = 'Falha controlada de unicidade da R04';
                END IF;
                RETURN NEW;
            END;
            $$
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON account
            FOR EACH ROW
            EXECUTE FUNCTION {function_name}()
            """
        )

    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON account"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )

__all__ = [name for name in globals() if not name.startswith("__")]
