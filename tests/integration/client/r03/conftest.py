"""Fixtures compartilhadas somente pelos testes da R03."""

from os import environ
from typing import Iterator

import pytest
from sqlalchemy import create_engine, make_url
from sqlalchemy.engine import Engine

from tests.utils import DbUtils


@pytest.fixture(scope="module")
def app_db_engine() -> Iterator[Engine]:
    """Abre conexões de leitura no mesmo banco usado pela API."""
    app_url = make_url(DbUtils.database_url())
    test_database_url = environ.get("TEST_DATABASE_URL")

    if app_url.database != "bootcamp" or app_url.database.endswith("_test"):
        pytest.fail("A verificação da R03 deve consultar o banco bootcamp da API.")
    if test_database_url and app_url == make_url(test_database_url):
        pytest.fail("O banco da API não pode ser TEST_DATABASE_URL.")

    engine = create_engine(app_url)
    try:
        yield engine
    finally:
        engine.dispose()
