from os import environ
from pathlib import Path

from sqlalchemy import create_engine, make_url
from sqlalchemy.exc import OperationalError


RESET_QUERIES = [
    "DROP SCHEMA public CASCADE;",
    "CREATE SCHEMA public;",
    "GRANT ALL ON SCHEMA public TO CURRENT_USER;",
    "GRANT ALL ON SCHEMA public TO public;",
]

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_FILE = PROJECT_ROOT / "database" / "database.sql"

DEFAULT_DATABASE_URL = "postgresql+psycopg2://bootcamp:bootcamp@localhost:55433/bootcamp"

DATABASE_OFFLINE = (
    "Não consegui falar com o banco em {host}:{port}.\n"
    "Suba a stack isolada de teste com: docker compose up -d --build --wait\n"
    "Confira a porta configurada em TEST_DATABASE_URL."
)


class DbUtils:
    """Ferramentas de banco usadas pelos testes de integração."""

    @staticmethod
    def database_url() -> str:
        """Devolve a URL usada pela API e pelos testes HTTP do exemplo."""
        return environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

    @staticmethod
    def reset_schema(database_url: str) -> None:
        """Apaga `public` e instala o ERD apenas em um banco descartável *_test.

        A URL é explícita porque o reset não pode escolher o banco da API.
        Isto não é rollback transacional: todas as tabelas desse schema
        são removidas antes de executar `database/database.sql`.
        """
        database_name = make_url(database_url).database
        if not database_name or not database_name.endswith("_test"):
            raise ValueError("reset_schema exige um banco cujo nome termina em _test")

        engine = create_engine(database_url, isolation_level="AUTOCOMMIT")

        try:
            with engine.connect() as connection:
                for query in RESET_QUERIES:
                    connection.exec_driver_sql(query)

                connection.exec_driver_sql(SCHEMA_FILE.read_text())
        except OperationalError:
            message = DATABASE_OFFLINE.format(host=engine.url.host, port=engine.url.port)
            raise RuntimeError(message) from None
        finally:
            engine.dispose()
