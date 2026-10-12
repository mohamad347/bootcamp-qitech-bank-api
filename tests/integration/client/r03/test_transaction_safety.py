"""Concorrência e atomicidade da transição de status da R03."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy.engine import Engine

from tests.integration.client.r03.support import (
    CONCURRENT_PROVIDER_DELAY_MILLISECONDS,
    analyze_client,
    assert_client_remains_pending,
    create_pending_individual,
    expect_client_analysis,
    expect_provider_response,
    get_client_lifecycle_summary,
    provider_request,
    reject_next_status_event_for_client,
)
from tests.utils.mockserver import MockServer
from tests.utils.requisition import BaseConnectorResponse


def test_concurrent_analysis_allows_only_one_status_transition(
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
        delay_milliseconds=CONCURRENT_PROVIDER_DELAY_MILLISECONDS,
    )

    start_gate = Barrier(3)

    def send_analysis() -> BaseConnectorResponse:
        start_gate.wait(timeout=5)
        return analyze_client(client_key)

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(send_analysis) for _ in range(2)]
        start_gate.wait(timeout=5)
        responses = [future.result(timeout=15) for future in futures]

    assert sorted(response.response_status for response in responses) == [200, 409]

    successful_response = next(
        response for response in responses if response.response_status == 200
    )
    conflict_response = next(
        response for response in responses if response.response_status == 409
    )
    assert successful_response.response_json == {
        "client_key": client_key,
        "status": "ACTIVE",
    }
    assert conflict_response.response_json["code"] == "CLI0002"
    MockServer.verify_exactly(expected_provider_request, count=2)
    assert get_client_lifecycle_summary(app_db_engine, client_key) == {
        "status": "ACTIVE",
        "event_count": 2,
    }


def test_event_failure_rolls_back_client_status_change(
    app_db_engine: Engine,
) -> None:
    MockServer.reset()
    client_key, normalized_cpf = create_pending_individual()
    expected_provider_request = provider_request(
        client_key,
        "INDIVIDUAL",
        normalized_cpf,
    )
    expect_client_analysis(
        expected_request=expected_provider_request,
        decision="APPROVE",
        reason=None,
    )

    with reject_next_status_event_for_client(app_db_engine, client_key):
        response = analyze_client(client_key)

    assert response.response_status == 500
    assert response.response_json["code"] == "QIT000500"
    MockServer.verify_exactly(expected_provider_request, count=1)
    assert_client_remains_pending(app_db_engine, client_key)
