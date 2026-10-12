import asyncio
import io
import json
import logging

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

import database
from app import create_app
from constants import INTERNAL_TOKEN
from utils.logger import JSONLogFormatter, RequestIdFilter


async def _request(application):
    messages = []
    sent = False

    async def receive():
        nonlocal sent
        if sent:
            return {"type": "http.disconnect"}
        sent = True
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        messages.append(message)

    await application(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/database-timeout",
            "raw_path": b"/database-timeout",
            "query_string": b"",
            "headers": [(b"internal-token", INTERNAL_TOKEN.encode("latin-1"))],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )
    start = next(message for message in messages if message["type"] == "http.response.start")
    body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    headers = {
        key.decode("latin-1").lower(): value.decode("latin-1")
        for key, value in start["headers"]
    }
    return start["status"], headers, json.loads(body)


def test_database_timeout_and_rollback_are_logged_once(
    schema_engine,
    monkeypatch,
):
    monkeypatch.setattr(
        database,
        "SessionLocal",
        sessionmaker(bind=schema_engine, autoflush=False),
    )
    application = create_app()

    async def force_statement_timeout():
        session = database.get_context().get_or_create_session()
        session.execute(text("SET LOCAL statement_timeout = '50ms'"))
        session.execute(text("SELECT pg_sleep(0.2)"))

    application.add_api_route(
        "/database-timeout",
        force_statement_timeout,
        methods=["GET"],
    )

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONLogFormatter())
    handler.addFilter(RequestIdFilter())
    root_logger = logging.getLogger()
    previous_handlers = root_logger.handlers[:]
    previous_level = root_logger.level
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)
    try:
        status, response_headers, body = asyncio.run(_request(application))
    finally:
        root_logger.handlers = previous_handlers
        root_logger.setLevel(previous_level)

    events = [json.loads(line) for line in stream.getvalue().splitlines()]
    names = [event["event"] for event in events]
    assert status == 500
    assert body["code"] == "QIT000500"
    assert names == [
        "request.started",
        "database.timeout",
        "database.rollback",
        "request.failed",
    ]
    request_id = response_headers["x-request-id"]
    assert {event["request_id"] for event in events} == {request_id}

    timeout_event = events[1]
    assert timeout_event["level"] == "ERROR"
    assert timeout_event["timeout_type"] == "statement"
    assert timeout_event["exception_type"] == "QueryCanceled"
    assert timeout_event["sqlstate"] == "57014"
    assert timeout_event["operation"] == "/database-timeout"

    rollback_events = [event for event in events if event["event"] == "database.rollback"]
    assert len(rollback_events) == 1
    assert rollback_events[0]["level"] == "WARNING"
    assert rollback_events[0]["reason_type"] == "timeout"
