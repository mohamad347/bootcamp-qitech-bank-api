"""Cen?rios da R01 organizados por comportamento."""

from .support import *


class TestCreateClient:
    def test_rejects_missing_internal_token(
        self, individual_payload: dict[str, str]
    ) -> None:
        response = ClientRequisition.send(
            "POST", "/client", payload=individual_payload
        )

        assert response.response_status == 403
        assert response.response_json["code"] == "QIT000002"

    def test_rejects_invalid_internal_token(
        self, individual_payload: dict[str, str]
    ) -> None:
        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": f"{INTERNAL_TOKEN}-invalid"},
        )

        assert response.response_status == 403
        assert response.response_json["code"] == "QIT000002"
