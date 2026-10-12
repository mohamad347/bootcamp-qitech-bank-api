"""Helpers coesos e locais da rota R09."""

from .base import *


def _patch(client_key: str, status: str, reason: str = "Motivo operacional"):
    return ClientRequisition.send(
        "PATCH",
        f"/client/{client_key}",
        payload={"status": status, "reason": reason},
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )


def _assert_error(response, status: int, code: str) -> None:
    assert response.response_status == status
    assert set(response.response_json) == {
        "title",
        "description",
        "translation",
        "code",
    }
    assert response.response_json["code"] == code

__all__ = [name for name in globals() if not name.startswith("__")]
