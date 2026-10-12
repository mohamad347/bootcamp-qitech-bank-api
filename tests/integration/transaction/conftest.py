from collections.abc import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine, make_url

from tests.integration.transaction.support import create_account
from tests.utils import DbUtils


@pytest.fixture(scope="module")
def api_database_engine() -> Iterator[Engine]:
    api_url = make_url(DbUtils.database_url())
    assert api_url.database == "bootcamp"
    assert api_url.host in {"localhost", "127.0.0.1"}

    engine = create_engine(api_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def active_account_key(api_database_engine: Engine) -> str:
    return create_account(api_database_engine)
