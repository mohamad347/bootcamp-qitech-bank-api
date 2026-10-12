"""Validação e resiliência do contrato com o Analysis Provider."""

import pytest
from sqlalchemy.engine import Engine

from tests.integration.client.r03.support import (
    ANALYSIS_PROVIDER_TIMEOUT_SECONDS,
    analyze_client,
    assert_client_remains_pending,
    create_pending_individual,
    expect_provider_response,
    provider_request,
)
from tests.utils.mockserver import MockServer


@pytest.mark.parametrize(
    "provider_body",
    [
        {"reason": None},
        {"decision": "MAYBE", "reason": None},
        {"decision": "REJECT"},
        {"decision": "REJECT", "reason": None},
        {"decision": "REJECT", "reason": "   "},
        {"decision": "REJECT", "reason": "R" * 501},
    ],
    ids=[
        "missing-decision",
        "invalid-decision",
        "missing-reason",
        "null-reason",
        "blank-reason",
        "reason-too-long",
    ],
)
def test_invalid_provider_response_does_not_change_client(
    app_db_engine: Engine,
    provider_body: dict,
) -> None:
    MockServer.reset()

    client_key, normalized_cpf = create_pending_individual()
    expected_provider_request = provider_request(
        client_key,
        "INDIVIDUAL",
        normalized_cpf,
    )
    expect_provider_response(expected_provider_request, provider_body)

    analysis_response = analyze_client(client_key)

    assert analysis_response.response_status == 500
    assert analysis_response.response_json["code"] == "QIT000500"
    MockServer.verify_exactly(expected_provider_request, count=1)
    assert_client_remains_pending(app_db_engine, client_key)


@pytest.mark.parametrize(
    ("provider_status", "provider_body"),
    [
        (500, {"error": "provider unavailable"}),
        (200, "this is not valid JSON"),
    ],
    ids=["provider-http-500", "provider-invalid-json"],
)
def test_provider_failure_does_not_change_client(
    app_db_engine: Engine,
    provider_status: int,
    provider_body: dict | str,
) -> None:
    MockServer.reset()
    client_key, normalized_cpf = create_pending_individual()
    expected_provider_request = provider_request(
        client_key,
        "INDIVIDUAL",
        normalized_cpf,
    )
    expect_provider_response(
        expected_request=expected_provider_request,
        response_body=provider_body,
        status_code=provider_status,
    )

    response = analyze_client(client_key)

    assert response.response_status == 500
    assert response.response_json["code"] == "QIT000500"
    MockServer.verify_exactly(expected_provider_request, count=1)
    assert_client_remains_pending(app_db_engine, client_key)


def test_provider_timeout_does_not_change_client(
    app_db_engine: Engine,
) -> None:
    MockServer.reset()
    client_key, normalized_cpf = create_pending_individual()
    expected_provider_request = provider_request(
        client_key,
        "INDIVIDUAL",
        normalized_cpf,
    )
    expect_provider_response(
        expected_request=expected_provider_request,
        response_body={"decision": "APPROVE", "reason": None},
        delay_milliseconds=(ANALYSIS_PROVIDER_TIMEOUT_SECONDS + 1) * 1_000,
    )

    response = analyze_client(client_key)

    assert response.response_status == 500
    assert response.response_json["code"] == "QIT000500"
    MockServer.verify_exactly(expected_provider_request, count=1)
    assert_client_remains_pending(app_db_engine, client_key)
