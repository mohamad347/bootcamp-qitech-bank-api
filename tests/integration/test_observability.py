import asyncio
import io
import json
import logging
from uuid import UUID, uuid4

import pytest

from app import create_app
from constants import INTERNAL_TOKEN
from errors.base_error import InvalidSchema
from utils.logger import JSONLogFormatter, RequestIdFilter
from utils.request_context import NO_REQUEST_ID, get_request_id


async def _asgi_request(application, method, path, *, headers=None, body=b"", query=b""):
    messages = []
    request_sent = False

    async def receive():
        nonlocal request_sent
        if request_sent:
            return {"type": "http.disconnect"}
        request_sent = True
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        messages.append(message)

    encoded_headers = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    await application(
        {
            "type": "http",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode("ascii"),
            "query_string": query,
            "headers": encoded_headers,
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
        },
        receive,
        send,
    )

    start = next(message for message in messages if message["type"] == "http.response.start")
    response_body = b"".join(
        message.get("body", b"")
        for message in messages
        if message["type"] == "http.response.body"
    )
    response_headers = {
        name.decode("latin-1").lower(): value.decode("latin-1")
        for name, value in start["headers"]
    }
    return start["status"], response_headers, response_body


@pytest.fixture
def structured_logs():
    stream = io.StringIO()
    stream.records = []
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONLogFormatter())
    handler.addFilter(RequestIdFilter())

    class RecordCollector(logging.Filter):
        def filter(self, record):
            stream.records.append(record)
            return True

    handler.addFilter(RecordCollector())

    root_logger = logging.getLogger()
    previous_handlers = root_logger.handlers[:]
    previous_level = root_logger.level
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.DEBUG)

    try:
        yield stream
    finally:
        root_logger.handlers = previous_handlers
        root_logger.setLevel(previous_level)


def _events(stream):
    return [
        event
        for line in stream.getvalue().splitlines()
        if line
        for event in [json.loads(line)]
        if event.get("event", "").startswith("request.")
    ]


def _terminal_events(events):
    return [event for event in events if event.get("event") in {
        "request.finished", "request.rejected", "request.failed"
    }]


def _application_with_test_routes():
    application = create_app()

    async def reject(account_key: str):
        raise InvalidSchema("invalid observability payload")

    async def fail(account_key: str):
        raise RuntimeError("controlled observability failure")

    async def accept(account_key: str):
        return {"ok": True}

    application.add_api_route("/observability/{account_key}/reject", reject, methods=["GET"])
    application.add_api_route("/observability/{account_key}/fail", fail, methods=["GET"])
    application.add_api_route("/observability/{account_key}", accept, methods=["POST"])
    return application


@pytest.mark.parametrize("received", [None, "caller_request-42", "bad id with spaces"])
def test_request_id_and_json_lifecycle(received, structured_logs):
    application = _application_with_test_routes()
    headers = {"INTERNAL-TOKEN": INTERNAL_TOKEN}
    if received is not None:
        headers["X-Request-ID"] = received

    status, response_headers, _ = asyncio.run(
        _asgi_request(application, "GET", "/observability/missing/reject", headers=headers)
    )

    request_id = response_headers["x-request-id"]
    if received == "caller_request-42":
        assert request_id == received
    else:
        UUID(request_id)
        assert request_id != received

    events = _events(structured_logs)
    assert [event["event"] for event in events] == ["request.started", "request.rejected"]
    assert {event["request_id"] for event in events} == {request_id}
    assert status == 400
    assert events[1]["route"] == "/observability/{account_key}/reject"
    assert events[1]["error_code"] == "QIT000001"
    assert events[1]["level"] == "INFO"
    assert len(_terminal_events(events)) == 1
    assert get_request_id() == NO_REQUEST_ID

def test_forbidden_has_request_id_and_warning_terminal(structured_logs):
    application = _application_with_test_routes()

    status, response_headers, body = asyncio.run(
        _asgi_request(application, "GET", "/observability/value/reject")
    )

    events = _events(structured_logs)
    assert status == 403
    assert json.loads(body)["code"] == "QIT000002"
    assert response_headers["x-request-id"] == events[0]["request_id"] == events[1]["request_id"]
    assert events[1]["event"] == "request.rejected"
    assert events[1]["level"] == "WARNING"
    assert events[1]["error_code"] == "QIT000002"
    assert len(_terminal_events(events)) == 1


def test_unexpected_error_has_header_response_and_single_failed_terminal(structured_logs):
    application = _application_with_test_routes()

    status, response_headers, body = asyncio.run(
        _asgi_request(
            application,
            "GET",
            "/observability/value/fail",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
    )

    events = _events(structured_logs)
    request_id = response_headers["x-request-id"]
    assert status == 500
    assert json.loads(body)["code"] == "QIT000500"
    assert [event["event"] for event in events] == ["request.started", "request.failed"]
    assert events[1]["level"] == "ERROR"
    assert events[1]["exception_type"] == "RuntimeError"
    assert events[1]["route"] == "/observability/{account_key}/fail"
    assert events[1]["request_id"] == request_id
    assert len(_terminal_events(events)) == 1
    failed_record = next(
        record for record in structured_logs.records if getattr(record, "event", None) == "request.failed"
    )
    assert failed_record.exc_info is not None


def test_logs_do_not_expose_request_data_or_real_path(structured_logs):
    application = _application_with_test_routes()
    real_key = str(uuid4())
    secrets = {
        "cpf": "99999999999",
        "cnpj": "99999999999999",
        "email": "sentinel@example.invalid",
        "payload": "SECRET_BODY_SENTINEL",
        "query": "SECRET_QUERY_SENTINEL",
    }
    body = json.dumps(secrets).encode("utf-8")

    status, _, _ = asyncio.run(
        _asgi_request(
            application,
            "POST",
            f"/observability/{real_key}",
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN, "content-type": "application/json"},
            body=body,
            query=f"token={secrets['query']}".encode("ascii"),
        )
    )

    raw_logs = structured_logs.getvalue()
    terminal = _terminal_events(_events(structured_logs))[0]
    assert status == 200
    assert terminal["route"] == "/observability/{account_key}"
    assert real_key not in raw_logs
    for secret in (*secrets.values(), INTERNAL_TOKEN):
        assert secret not in raw_logs


def test_concurrent_requests_keep_request_ids_isolated_and_reset_context(structured_logs):
    application = _application_with_test_routes()
    request_ids = ("concurrent_A", "concurrent_B")

    async def run_both():
        return await asyncio.gather(*(
            _asgi_request(
                application,
                "GET",
                f"/observability/{request_id}/reject",
                headers={"INTERNAL-TOKEN": INTERNAL_TOKEN, "X-Request-ID": request_id},
            )
            for request_id in request_ids
        ))

    responses = asyncio.run(run_both())
    events = _events(structured_logs)

    assert [response[0] for response in responses] == [400, 400]
    for request_id, response in zip(request_ids, responses):
        assert response[1]["x-request-id"] == request_id
        matching = [event for event in events if event["request_id"] == request_id]
        assert [event["event"] for event in matching] == ["request.started", "request.rejected"]
    assert get_request_id() == NO_REQUEST_ID
