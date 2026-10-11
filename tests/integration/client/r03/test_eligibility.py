"""Validações locais executadas antes de chamar o provider."""

from uuid import uuid4

import pytest
from sqlalchemy.engine import Engine

from tests.integration.client.r03.support import (
    analyze_client,
    create_pending_individual,
    get_client_status,
    prepare_client_status,
    verify_provider_was_not_called,
)
from tests.utils import INTERNAL_TOKEN
from tests.utils.mockserver import MockServer
from tests.utils.requisition import ClientRequisition


@pytest.mark.parametrize(
    "current_status",
    ["ACTIVE", "REJECTED", "INACTIVE"],
)
def test_non_pending_client_returns_conflict_without_calling_provider(
    app_db_engine: Engine,
    current_status: str,
) -> None:
    client_key, _ = create_pending_individual()
    prepare_client_status(app_db_engine, client_key, current_status)
    MockServer.reset()

    response = analyze_client(client_key)

    assert response.response_status == 409
    assert response.response_json["code"] == "CLI0002"
    verify_provider_was_not_called()
    assert get_client_status(app_db_engine, client_key) == current_status


def test_unknown_client_returns_not_found_without_calling_provider() -> None:
    MockServer.reset()
    unknown_client_key = str(uuid4())

    response = analyze_client(unknown_client_key)

    assert response.response_status == 404
    assert response.response_json["code"] == "CLI0001"
    verify_provider_was_not_called()


def test_malformed_client_key_returns_bad_request_without_calling_provider() -> None:
    MockServer.reset()

    response = analyze_client("not-a-uuid")

    assert response.response_status == 400
    assert response.response_json["code"] == "QIT000010"
    verify_provider_was_not_called()


def test_invalid_internal_token_does_not_call_provider() -> None:
    MockServer.reset()

    response = ClientRequisition.send(
        "POST",
        f"/client/{uuid4()}/analysis",
        headers={"INTERNAL-TOKEN": f"{INTERNAL_TOKEN}-invalid"},
    )

    assert response.response_status == 403
    assert response.response_json["code"] == "QIT000002"
    verify_provider_was_not_called()
