from concurrent.futures import ThreadPoolExecutor
from threading import Event
import time

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from database import create_database_engine, database_connect_args
from utils.database_errors import classify_database_timeout


def test_engine_configures_connect_lock_and_statement_timeouts(schema_engine):
    database_url = schema_engine.url.render_as_string(hide_password=False)
    configured_engine = create_database_engine(database_url)
    try:
        connect_options = database_connect_args()
        assert connect_options["connect_timeout"] == 5
        assert "lock_timeout=3000ms" in connect_options["options"]
        assert "statement_timeout=10000ms" in connect_options["options"]

        with configured_engine.connect() as connection:
            assert connection.exec_driver_sql("SHOW lock_timeout").scalar_one() == "3s"
            assert connection.exec_driver_sql("SHOW statement_timeout").scalar_one() == "10s"
    finally:
        configured_engine.dispose()


def test_lock_timeout_uses_sqlstate_55p03(schema_engine):
    database_url = schema_engine.url.render_as_string(hide_password=False)
    configured_engine = create_database_engine(database_url)
    started = Event()
    backend_pid = []

    try:
        with configured_engine.connect() as blocker:
            blocker_transaction = blocker.begin()
            blocker_pid = blocker.execute(text("SELECT pg_backend_pid()")).scalar_one()
            blocker.exec_driver_sql("LOCK TABLE client_status IN ACCESS EXCLUSIVE MODE")

            def wait_for_locked_table():
                with configured_engine.connect() as waiter:
                    waiter.exec_driver_sql("SET LOCAL lock_timeout = '1000ms'")
                    backend_pid.append(
                        waiter.execute(text("SELECT pg_backend_pid()")).scalar_one()
                    )
                    started.set()
                    waiter.execute(text("SELECT 1 FROM client_status LIMIT 1"))

            with ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(wait_for_locked_table)
                assert started.wait(timeout=2)

                blocked = False
                deadline = time.monotonic() + 0.8
                with schema_engine.connect() as observer:
                    while time.monotonic() < deadline:
                        observer.exec_driver_sql("SELECT pg_stat_clear_snapshot()")
                        blockers = observer.execute(
                            text("SELECT pg_blocking_pids(:pid)"),
                            {"pid": backend_pid[0]},
                        ).scalar_one()
                        if blocker_pid in blockers:
                            blocked = True
                            break
                        time.sleep(0.02)
                assert blocked

                with pytest.raises(OperationalError) as captured:
                    future.result(timeout=3)

            details = classify_database_timeout(captured.value)
            assert details is not None
            assert details.timeout_type == "lock"
            assert details.sqlstate == "55P03"
            assert details.exception_type == "LockNotAvailable"
            blocker_transaction.rollback()
    finally:
        configured_engine.dispose()


def test_statement_timeout_uses_sqlstate_57014(schema_engine):
    database_url = schema_engine.url.render_as_string(hide_password=False)
    configured_engine = create_database_engine(database_url)
    try:
        with configured_engine.connect() as connection:
            connection.exec_driver_sql("SET LOCAL statement_timeout = '100ms'")
            with pytest.raises(OperationalError) as captured:
                connection.execute(text("SELECT pg_sleep(0.5)"))

        details = classify_database_timeout(captured.value)
        assert details is not None
        assert details.timeout_type == "statement"
        assert details.sqlstate == "57014"
        assert details.exception_type == "QueryCanceled"
    finally:
        configured_engine.dispose()
