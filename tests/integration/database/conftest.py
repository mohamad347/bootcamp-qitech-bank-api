"""Recursos compartilhados pelos testes do schema físico."""

from os import environ

import pytest
from sqlalchemy import create_engine, make_url

from tests.utils import DbUtils


@pytest.fixture(scope="session")
def schema_engine():
    """Instala o ERD uma vez em TEST_DATABASE_URL e entrega a engine à suíte.

    O reset apaga `public`; por isso a URL deve apontar para um banco
    descartável, terminado em `_test` e diferente do banco da aplicação.
    """
    raw_url = environ.get("TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail("Defina TEST_DATABASE_URL para um banco descartável antes de rodar os testes de schema.")

    test_url = make_url(raw_url)
    if not test_url.database or not test_url.database.endswith("_test"):
        pytest.fail("TEST_DATABASE_URL precisa apontar para um banco cujo nome termina em _test.")
    if test_url == make_url(DbUtils.database_url()):
        pytest.fail("TEST_DATABASE_URL e DATABASE_URL não podem apontar para o mesmo banco.")

    DbUtils.reset_schema(raw_url)
    engine = create_engine(raw_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def db_connection(schema_engine):
    """Entrega uma conexão transacional e desfaz as linhas após cada teste."""
    with schema_engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()
