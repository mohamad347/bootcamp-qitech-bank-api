"""Cen?rios de R09 organizados por comportamento."""

from .support import *


@pytest.mark.parametrize(
    ("initial_status", "target_status"),
    [
        ("PENDING", "PENDING"),
        ("ACTIVE", "ACTIVE"),
        ("REJECTED", "REJECTED"),
        ("INACTIVE", "INACTIVE"),
        ("PENDING", "ACTIVE"),
        ("PENDING", "REJECTED"),
        ("REJECTED", "ACTIVE"),
        ("REJECTED", "INACTIVE"),
        ("ACTIVE", "PENDING"),
        ("ACTIVE", "REJECTED"),
        ("INACTIVE", "PENDING"),
        ("INACTIVE", "REJECTED"),
    ],
)
def test_patch_client_rejects_forbidden_transition_without_side_effects(
    api_database_engine: Engine,
    initial_status: str,
    target_status: str,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, initial_status)
    before = _snapshot(api_database_engine, client_key)

    response = _patch(client_key, target_status)

    _assert_error(response, 409, "CLI0002")
    assert _snapshot(api_database_engine, client_key) == before


@pytest.mark.parametrize("account_status", ["ACTIVE", "INACTIVE", "CLOSED"])
def test_patch_client_requires_r06_when_any_account_exists(
    api_database_engine: Engine,
    account_status: str,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")
    _open_account(client_key, account_status)
    before = _snapshot(api_database_engine, client_key)
    target_status = "INACTIVE" if account_status == "ACTIVE" else "ACTIVE"

    response = _patch(client_key, target_status)

    _assert_error(response, 409, "CLI0009")
    assert _snapshot(api_database_engine, client_key) == before


def test_r09_refusal_preserves_r06_as_account_lifecycle_authority(
    api_database_engine: Engine,
) -> None:
    client_key, _ = _create_client_in_status(api_database_engine, "ACTIVE")
    account_key = _open_account(client_key)
    direct = _patch(client_key, "INACTIVE", "Tentativa direta")
    _assert_error(direct, 409, "CLI0009")

    coordinated = ClientRequisition.send(
        "PATCH",
        f"/account/{account_key}",
        payload={"status": "INACTIVE", "reason": "Lifecycle coordenado"},
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    assert coordinated.response_status == 200
    after = _snapshot(api_database_engine, client_key)
    assert (after["client_status"], after["account_status"]) == (
        "INACTIVE",
        "INACTIVE",
    )
