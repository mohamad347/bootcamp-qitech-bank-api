"""Primeiro ciclo TDD da R03: Analysis Provider aprova um CLIENT PENDING."""

import json
from os import environ
from uuid import uuid4

import requests

from tests.utils import INTERNAL_TOKEN, RandomGenerator
from tests.utils.requisition import ClientRequisition


MOCKSERVER_URL = environ.get("MOCKSERVER_URL", "http://127.0.0.1:1080")
MOCKSERVER_CONTROL_TIMEOUT_SECONDS = 5


def _reset_mockserver() -> None:
    response = requests.put(
        f"{MOCKSERVER_URL}/mockserver/reset",
        timeout=MOCKSERVER_CONTROL_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def _expect_client_analysis_approve() -> None:
    expectation = {
        "httpRequest": {
            "method": "POST",
            "path": "/v1/client-analysis",
        },
        "httpResponse": {
            "statusCode": 200,
            "headers": {"Content-Type": ["application/json"]},
            "body": json.dumps({"decision": "APPROVE", "reason": None}),
        },
    }

    response = requests.put(
        f"{MOCKSERVER_URL}/mockserver/expectation",
        json=expectation,
        timeout=MOCKSERVER_CONTROL_TIMEOUT_SECONDS,
    )
    response.raise_for_status()


def test_approve_pending_client_returns_200() -> None:
    _reset_mockserver()

    client_payload = {
        "client_type": "INDIVIDUAL",
        "email": f"r03.approve.{uuid4()}@example.com",
        "cpf": RandomGenerator.generate_cpf(),
        "full_name": "Cliente R03",
        "birth_date": "2000-01-01",
        "timezone": "America/Sao_Paulo",
    }
    create_response = ClientRequisition.send(
        "POST",
        "/client",
        payload=client_payload,
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert create_response.response_status == 201

    _expect_client_analysis_approve()

    client_key = create_response.response_json["client_key"]
    analysis_response = ClientRequisition.send(
        "POST",
        f"/client/{client_key}/analysis",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    assert analysis_response.response_status == 200
