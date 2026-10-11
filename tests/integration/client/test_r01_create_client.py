from uuid import UUID, uuid4

import pytest

from tests.utils import INTERNAL_TOKEN, RandomGenerator
from tests.utils.requisition import ClientRequisition


@pytest.fixture
def individual_payload() -> dict[str, str]:
    return {
        "client_type": "INDIVIDUAL",
        "email": f"r01.pf.valid.{uuid4()}@example.com",
        "cpf": RandomGenerator.generate_cpf(),
        "full_name": "Joao Teste",
        "birth_date": "2000-01-01",
        "timezone": "America/Sao_Paulo",
    }


class TestCreateClient:
    @pytest.mark.parametrize("masked", [False, True], ids=["unmasked", "masked"])
    def test_create_valid_individual_client(
        self, masked: bool, individual_payload: dict[str, str]
    ) -> None:
        if not masked:
            cpf = individual_payload["cpf"]
            individual_payload["cpf"] = cpf.replace(".", "").replace("-", "")

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        assert response.response_status == 201

        response_body = response.response_json
        assert isinstance(response_body, dict)
        assert set(response_body) == {"client_key", "client_type", "status"}
        assert response_body["client_type"] == "INDIVIDUAL"
        assert response_body["status"] == "PENDING"
        assert isinstance(response_body["client_key"], str)
        assert isinstance(UUID(response_body["client_key"]), UUID)

    def test_rejects_missing_cpf(self, individual_payload: dict[str, str]) -> None:
        del individual_payload["cpf"]

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"

    def test_rejects_extra_property(self, individual_payload: dict[str, str]) -> None:
        payload = {**individual_payload, "campo_que_nao_existe": True}

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"

    def test_rejects_unknown_client_type(
        self, individual_payload: dict[str, str]
    ) -> None:
        individual_payload["client_type"] = "PERSON"

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"

    def test_rejects_structurally_invalid_cpf(
        self, individual_payload: dict[str, str]
    ) -> None:
        individual_payload["cpf"] = "123"

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"

    def test_rejects_structurally_invalid_email(
        self, individual_payload: dict[str, str]
    ) -> None:
        individual_payload["email"] = "email-sem-arroba"

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"

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
