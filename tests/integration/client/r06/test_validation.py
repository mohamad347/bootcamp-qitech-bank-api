"""Cen?rios de R06 organizados por comportamento."""

from .support import *


def test_patch_account_rejects_malformed_key() -> None:
    response = ClientRequisition.send(
        "PATCH",
        "/account/not-a-uuid",
        payload={"status": "INACTIVE", "reason": "Motivo"},
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_error(response, 400, "QIT000001")


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"reason": "Motivo"},
        {"status": None, "reason": "Motivo"},
        {"status": 1, "reason": "Motivo"},
        {"status": "active", "reason": "Motivo"},
        {"status": "INVALID", "reason": "Motivo"},
        {"status": "INACTIVE"},
        {"status": "INACTIVE", "reason": None},
        {"status": "INACTIVE", "reason": 1},
        {"status": "INACTIVE", "reason": ""},
        {"status": "INACTIVE", "reason": "   "},
        {"status": "INACTIVE", "reason": "X" * 501},
        {"status": "INACTIVE", "reason": "Motivo", "balance_cents": 0},
    ],
)
def test_patch_account_rejects_invalid_body(payload) -> None:
    response = ClientRequisition.send(
        "PATCH",
        f"/account/{uuid4()}",
        payload=payload,
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_error(response, 400, "QIT000001")


def test_patch_account_rejects_malformed_json() -> None:
    response = ClientRequisition.send(
        "PATCH",
        f"/account/{uuid4()}",
        data="{",
        headers={
            "INTERNAL-TOKEN": INTERNAL_TOKEN,
            "Content-Type": "application/json",
        },
    )
    _assert_error(response, 400, "QIT000001")


@pytest.mark.parametrize(
    ("account_key", "payload", "headers"),
    [
        (str(uuid4()), {"status": "INACTIVE", "reason": "Motivo"}, {}),
        (str(uuid4()), {"status": "INACTIVE", "reason": "Motivo"}, {"INTERNAL-TOKEN": "invalid"}),
        ("not-a-uuid", {"status": None}, {"INTERNAL-TOKEN": "invalid"}),
    ],
)
def test_patch_account_authentication_has_precedence(account_key, payload, headers) -> None:
    response = ClientRequisition.send(
        "PATCH", f"/account/{account_key}", payload=payload, headers=headers
    )
    _assert_error(response, 403, "QIT000002")


def test_patch_account_rejects_unknown_account_and_client_key() -> None:
    unknown = _patch(str(uuid4()), "INACTIVE")
    _assert_error(unknown, 404, "ACC0001")

    client_key, _ = _create_active_account_for_client_key_test()
    wrong_resource = _patch(client_key, "INACTIVE")
    _assert_error(wrong_resource, 404, "ACC0001")
