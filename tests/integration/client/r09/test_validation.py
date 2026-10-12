"""Cen?rios de R09 organizados por comportamento."""

from .support import *


def test_patch_client_rejects_malformed_key() -> None:
    response = _patch("not-a-uuid", "INACTIVE")

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
        {"status": True, "reason": "Motivo"},
        {"status": "active", "reason": "Motivo"},
        {"status": "CLOSED", "reason": "Motivo"},
        {"status": "UNKNOWN", "reason": "Motivo"},
        {"status": "INACTIVE"},
        {"status": "INACTIVE", "reason": None},
        {"status": "INACTIVE", "reason": 1},
        {"status": "INACTIVE", "reason": ""},
        {"status": "INACTIVE", "reason": "   "},
        {"status": "INACTIVE", "reason": "X" * 501},
        {"status": "INACTIVE", "reason": "Motivo", "email": "novo@example.com"},
    ],
)
def test_patch_client_rejects_invalid_body(payload) -> None:
    response = ClientRequisition.send(
        "PATCH",
        f"/client/{uuid4()}",
        payload=payload,
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    _assert_error(response, 400, "QIT000001")


def test_patch_client_rejects_malformed_json() -> None:
    response = ClientRequisition.send(
        "PATCH",
        f"/client/{uuid4()}",
        data="{",
        headers={
            "INTERNAL-TOKEN": INTERNAL_TOKEN,
            "Content-Type": "application/json",
        },
    )
    _assert_error(response, 400, "QIT000001")


@pytest.mark.parametrize(
    ("client_key", "payload", "headers"),
    [
        (str(uuid4()), {"status": "INACTIVE", "reason": "Motivo"}, {}),
        (
            str(uuid4()),
            {"status": "INACTIVE", "reason": "Motivo"},
            {"INTERNAL-TOKEN": "invalid"},
        ),
        ("not-a-uuid", {"status": None}, {"INTERNAL-TOKEN": "invalid"}),
    ],
)
def test_patch_client_authentication_has_precedence(
    client_key: str,
    payload,
    headers: dict,
) -> None:
    response = ClientRequisition.send(
        "PATCH",
        f"/client/{client_key}",
        payload=payload,
        headers=headers,
    )
    _assert_error(response, 403, "QIT000002")


def test_patch_client_rejects_unknown_client() -> None:
    response = _patch(str(uuid4()), "INACTIVE")
    _assert_error(response, 404, "CLI0001")
