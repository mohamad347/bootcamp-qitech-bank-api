"""Testes da R02: cen?rios organizados por comportamento."""

from .support import *


def test_get_client_rejects_malformed_uuid() -> None:
    response = ClientRequisition.send(
        "GET",
        "/client/not-a-uuid",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_error_response(response, 400, "QIT000001")


def test_get_client_returns_not_found_for_unknown_uuid() -> None:
    client_key = str(uuid4())
    response = ClientRequisition.send(
        "GET",
        f"/client/{client_key}",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    _assert_error_response(response, 404, "CLI0001")


def test_get_client_rejects_missing_internal_token(
    existing_individual_client_key: str,
) -> None:
    response = ClientRequisition.send(
        "GET",
        f"/client/{existing_individual_client_key}",
    )

    _assert_error_response(response, 403, "QIT000002")


def test_get_client_rejects_invalid_internal_token(
    existing_individual_client_key: str,
) -> None:
    response = ClientRequisition.send(
        "GET",
        f"/client/{existing_individual_client_key}",
        headers={"INTERNAL-TOKEN": f"{INTERNAL_TOKEN}-invalid"},
    )

    _assert_error_response(response, 403, "QIT000002")


def test_get_client_checks_auth_before_unknown_client_lookup() -> None:
    unknown_client_key = str(uuid4())
    response = ClientRequisition.send(
        "GET",
        f"/client/{unknown_client_key}",
        headers={"INTERNAL-TOKEN": "invalid-token"},
    )

    _assert_error_response(response, 403, "QIT000002")


def test_get_client_checks_auth_before_malformed_uuid_validation() -> None:
    response = ClientRequisition.send(
        "GET",
        "/client/not-a-uuid",
        headers={"INTERNAL-TOKEN": "invalid-token"},
    )

    _assert_error_response(response, 403, "QIT000002")
