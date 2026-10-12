"""Cen?rios de R09 organizados por comportamento."""

from .support import *


@pytest.mark.parametrize(
    ("client_type", "initial_status", "target_status"),
    [
        ("INDIVIDUAL", "REJECTED", "PENDING"),
        ("INDIVIDUAL", "ACTIVE", "INACTIVE"),
        ("COMPANY", "INACTIVE", "ACTIVE"),
    ],
)
def test_patch_client_allowed_transitions_update_status_and_create_one_event(
    api_database_engine: Engine,
    client_type: str,
    initial_status: str,
    target_status: str,
) -> None:
    client_key, _ = _create_client_in_status(
        api_database_engine,
        initial_status,
        client_type,
    )
    before = _snapshot(api_database_engine, client_key)

    response = _patch(client_key, target_status, "  Solicitação operacional  ")

    assert response.response_status == 200
    assert response.response_json == {
        "client_key": client_key,
        "status": target_status,
    }
    after = _snapshot(api_database_engine, client_key)
    assert after["client_status"] == target_status
    assert after["client_event_count"] == before["client_event_count"] + 1
    assert after["account_count"] == before["account_count"] == 0
    assert after["client_type"] == before["client_type"] == client_type
    assert after["email"] == before["email"]
    assert after["timezone"] == before["timezone"]
    assert after["created_at"] == before["created_at"]
    assert after["updated_at"] > before["updated_at"]
    assert after["account_event_count"] == before["account_event_count"] == 0
    assert after["entry_count"] == before["entry_count"] == 0
    assert after["transaction_count"] == before["transaction_count"] == 0
    event = _events(api_database_engine, client_key)[-1]
    assert event["from_status"] == initial_status
    assert event["to_status"] == target_status
    assert event["actor_type"] == "INTERNAL"
    assert event["reason"] == "Solicitação operacional"
    assert event["created_at"] == after["updated_at"]
    assert event["created_at"].tzinfo is not None
    assert event["created_at"].utcoffset() == timezone.utc.utcoffset(
        event["created_at"]
    )


def test_patch_client_allows_reanalysis_without_artificial_limit(
    api_database_engine: Engine,
) -> None:
    MockServer.reset()
    client_key, _ = _create_client_in_status(api_database_engine, "REJECTED")
    first = _patch(client_key, "PENDING", " Primeira reanálise ")
    assert first.response_status == 200

    _transition_client_fixture(
        api_database_engine,
        client_key,
        "PENDING",
        "REJECTED",
    )
    before_second = _snapshot(api_database_engine, client_key)
    second = _patch(client_key, "PENDING", " Segunda reanálise ")

    assert second.response_status == 200
    assert second.response_json == {"client_key": client_key, "status": "PENDING"}
    after_second = _snapshot(api_database_engine, client_key)
    assert after_second["client_event_count"] == before_second["client_event_count"] + 1
    assert _events(api_database_engine, client_key)[-1]["reason"] == "Segunda reanálise"
    MockServer.verify_exactly(
        {"method": "POST", "path": "/v1/client-analysis"},
        count=0,
    )


def test_r02_reflects_status_changed_by_r09(api_database_engine: Engine) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")
    assert _patch(client_key, "INACTIVE").response_status == 200

    response = ClientRequisition.send(
        "GET",
        f"/client/{client_key}",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    assert response.response_status == 200
    assert response.response_json["status"] == "INACTIVE"


@pytest.mark.parametrize("reason", [" X ", f" {'R' * 500} "])
def test_patch_client_accepts_reason_boundaries_after_trimming(
    api_database_engine: Engine,
    reason: str,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")

    response = _patch(client_key, "INACTIVE", reason)

    assert response.response_status == 200
    assert _events(api_database_engine, client_key)[-1]["reason"] == reason.strip()
