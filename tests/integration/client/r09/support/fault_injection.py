"""Helpers coesos e locais da rota R09."""

from .base import *


@contextmanager
def _reject_status_event_for_client(
    engine: Engine,
    client_key: str,
) -> Iterator[None]:
    suffix = uuid4().hex
    function_name = f"r09_fail_event_function_{suffix}"
    trigger_name = f"r09_fail_event_trigger_{suffix}"
    with engine.begin() as connection:
        client_id = connection.execute(
            text(
                """
                SELECT id FROM client
                WHERE client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        connection.exec_driver_sql(
            f"""
            CREATE FUNCTION {function_name}() RETURNS trigger AS $$
            BEGIN
                IF NEW.client_id = {client_id} THEN
                    RAISE EXCEPTION 'R09 controlled event failure';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
            """
        )
        connection.exec_driver_sql(
            f"""
            CREATE TRIGGER {trigger_name}
            BEFORE INSERT ON client_status_event
            FOR EACH ROW EXECUTE FUNCTION {function_name}()
            """
        )
    try:
        yield
    finally:
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"DROP TRIGGER IF EXISTS {trigger_name} ON client_status_event"
            )
            connection.exec_driver_sql(
                f"DROP FUNCTION IF EXISTS {function_name}()"
            )

__all__ = [name for name in globals() if not name.startswith("__")]
