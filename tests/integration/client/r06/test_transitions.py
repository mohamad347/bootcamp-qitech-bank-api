"""Cen?rios de R06 organizados por comportamento."""

from .support import *


def test_patch_account_active_to_inactive_updates_both_resources(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    before = _snapshot(api_database_engine, account_key)

    response = ClientRequisition.send(
        "PATCH",
        f"/account/{account_key}",
        payload={"status": "INACTIVE", "reason": "  Solicitação operacional  "},
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    assert response.response_status == 200
    assert response.response_json == {"account_key": account_key, "status": "INACTIVE"}
    after = _snapshot(api_database_engine, account_key)
    assert after["account_status"] == "INACTIVE"
    assert after["client_status"] == "INACTIVE"
    assert after["balance_cents"] == before["balance_cents"]
    assert after["account_created_at"] == before["account_created_at"]
    assert after["client_created_at"] == before["client_created_at"]
    assert after["account_updated_at"] == after["client_updated_at"]
    assert after["entry_count"] == before["entry_count"] == 0
    assert after["transaction_count"] == before["transaction_count"] == 0
    assert after["account_event_count"] == before["account_event_count"] + 1
    assert after["client_event_count"] == before["client_event_count"] + 1
    account_events, client_events = _events(api_database_engine, account_key)
    account_event = account_events[-1]
    client_event = client_events[-1]
    for event in (account_event, client_event):
        assert event["from_status"] == "ACTIVE"
        assert event["to_status"] == "INACTIVE"
        assert event["actor_type"] == "INTERNAL"
        assert event["reason"] == "Solicitação operacional"
        assert event["created_at"].tzinfo is not None
        assert event["created_at"].utcoffset() == timezone.utc.utcoffset(event["created_at"])


def test_patch_company_account_inactive_to_active_accepts_500_character_reason(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine, "COMPANY")
    _prepare_inactive(account_key)
    before = _snapshot(api_database_engine, account_key)
    reason = "R" * 500

    response = _patch(account_key, "ACTIVE", f" {reason} ")

    assert response.response_status == 200
    assert response.response_json == {"account_key": account_key, "status": "ACTIVE"}
    after = _snapshot(api_database_engine, account_key)
    assert (after["account_status"], after["client_status"]) == ("ACTIVE", "ACTIVE")
    assert after["account_event_count"] == before["account_event_count"] + 1
    assert after["client_event_count"] == before["client_event_count"] + 1
    account_events, client_events = _events(api_database_engine, account_key)
    assert account_events[-1]["reason"] == reason
    assert client_events[-1]["reason"] == reason


def test_patch_account_active_to_closed_closes_account_and_inactivates_client(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    before = _snapshot(api_database_engine, account_key)

    response = _patch(account_key, "CLOSED", "Encerramento solicitado")

    assert response.response_status == 200
    assert response.response_json == {"account_key": account_key, "status": "CLOSED"}
    after = _snapshot(api_database_engine, account_key)
    assert (after["account_status"], after["client_status"]) == ("CLOSED", "INACTIVE")
    assert after["account_event_count"] == before["account_event_count"] + 1
    assert after["client_event_count"] == before["client_event_count"] + 1
    assert after["balance_cents"] == 0
    assert after["account_created_at"] == before["account_created_at"]
    assert after["client_created_at"] == before["client_created_at"]


def test_patch_account_inactive_to_closed_does_not_create_same_state_client_event(
    api_database_engine: Engine,
) -> None:
    _, account_key = _create_active_account(api_database_engine)
    _prepare_inactive(account_key)
    before = _snapshot(api_database_engine, account_key)

    response = _patch(account_key, "CLOSED", "Encerramento definitivo")

    assert response.response_status == 200
    after = _snapshot(api_database_engine, account_key)
    assert (after["account_status"], after["client_status"]) == ("CLOSED", "INACTIVE")
    assert after["account_event_count"] == before["account_event_count"] + 1
    assert after["client_event_count"] == before["client_event_count"]
    assert after["client_updated_at"] == before["client_updated_at"]


def test_r05_reflects_status_changed_by_r06(api_database_engine: Engine) -> None:
    _, account_key = _create_active_account(api_database_engine)
    assert _patch(account_key, "INACTIVE").response_status == 200

    response = ClientRequisition.send(
        "GET", f"/account/{account_key}", headers={"INTERNAL-TOKEN": INTERNAL_TOKEN}
    )

    assert response.response_status == 200
    assert response.response_json["status"] == "INACTIVE"
