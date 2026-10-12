"""Helpers coesos e locais da rota R04."""

from .base import *


@pytest.fixture(scope="module")
def api_database_engine() -> Iterator[Engine]:
    """Conecta apenas ao banco local da API, distinto do banco de schema."""
    api_url = make_url(DbUtils.database_url())
    test_url = make_url(environ["TEST_DATABASE_URL"])

    assert api_url.database == "bootcamp"
    assert api_url.host in {"localhost", "127.0.0.1"}
    assert test_url.database == "bootcamp_test"
    assert test_url.host in {"localhost", "127.0.0.1"}
    assert api_url != test_url

    engine = create_engine(api_url)
    try:
        with engine.connect() as connection:
            api_identity = connection.execute(
                text(
                    "SELECT current_database(), "
                    "(SELECT system_identifier::text FROM pg_control_system()), "
                    "inet_server_port()"
                )
            ).one()

        assert api_identity[0] == "bootcamp"
        assert api_identity[1]
        assert api_identity[2]

        test_engine = create_engine(test_url)
        try:
            with test_engine.connect() as connection:
                test_identity = connection.execute(
                    text(
                        "SELECT current_database(), "
                        "(SELECT system_identifier::text FROM pg_control_system()), "
                        "inet_server_port()"
                    )
                ).one()
        finally:
            test_engine.dispose()

        assert test_identity[0] == "bootcamp_test"
        assert test_identity[1]
        assert test_identity[2]
        assert api_identity[1] != test_identity[1]

        yield engine
    finally:
        engine.dispose()


def _get_client_account_summary(engine: Engine, client_key: str) -> dict:
    """Lê somente o estado físico ligado ao CLIENT do cenário."""
    with engine.connect() as connection:
        connection.exec_driver_sql("SET TRANSACTION READ ONLY")
        client = connection.execute(
            text(
                """
                SELECT status.enumerator AS status
                FROM client
                JOIN client_status AS status ON status.id = client.status_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).mappings().one()
        account_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM account
                JOIN client ON client.id = account.client_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        account_status = connection.execute(
            text(
                """
                SELECT status.enumerator
                FROM account
                JOIN account_status AS status ON status.id = account.status_id
                JOIN client ON client.id = account.client_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one_or_none()
        account_event_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM account_status_event AS event
                JOIN account ON account.id = event.account_id
                JOIN client ON client.id = account.client_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()
        client_event_count = connection.execute(
            text(
                """
                SELECT COUNT(*)
                FROM client_status_event AS event
                JOIN client ON client.id = event.client_id
                WHERE client.client_key = CAST(:client_key AS uuid)
                """
            ),
            {"client_key": client_key},
        ).scalar_one()

    return {
        "status": client["status"],
        "account_count": account_count,
        "account_status": account_status,
        "account_event_count": account_event_count,
        "client_event_count": client_event_count,
    }

__all__ = [name for name in globals() if not name.startswith("__")]
