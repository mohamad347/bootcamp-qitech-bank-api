"""Cen?rios da R01 organizados por comportamento."""

from .support import *


class TestCreateClient:
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

    def test_rejects_impossible_birth_date(
        self, individual_payload: dict[str, str]
    ) -> None:
        individual_payload["birth_date"] = "2000-02-30"

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"
        assert {"title", "description", "translation", "code"} <= set(
            response.response_json
        )

    def test_rejects_full_name_empty_after_trim(
        self, individual_payload: dict[str, str]
    ) -> None:
        individual_payload["full_name"] = "     "

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"
        assert {"title", "description", "translation", "code"} <= set(
            response.response_json
        )

    def test_rejects_company_without_legal_name(
        self, company_payload: dict[str, str]
    ) -> None:
        del company_payload["legal_name"]

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=company_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"
        assert {"title", "description", "translation", "code"} <= set(
            response.response_json
        )

    def test_rejects_company_legal_name_empty_after_trim(
        self, company_payload: dict[str, str]
    ) -> None:
        company_payload["legal_name"] = "     "

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=company_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"
        assert {"title", "description", "translation", "code"} <= set(
            response.response_json
        )

    def test_rejects_structurally_invalid_company_email(
        self, company_payload: dict[str, str]
    ) -> None:
        company_payload["email"] = "email-sem-arroba"

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=company_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"

    def test_rejects_company_with_individual_fields(
        self, company_payload: dict[str, str]
    ) -> None:
        company_payload["cpf"] = RandomGenerator.generate_cpf()

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=company_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"

    def test_rejects_email_above_254_character_limit(
        self, individual_payload: dict[str, str]
    ) -> None:
        local_part = f"{uuid4().hex}{'a' * 32}"
        individual_payload["email"] = (
            f"{local_part}@{'b' * 63}.{'c' * 63}.{'d' * 54}.example"
        )
        assert len(individual_payload["email"]) == 255

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"

    def test_rejects_full_name_above_200_character_limit(
        self, individual_payload: dict[str, str]
    ) -> None:
        individual_payload["full_name"] = "N" * 201

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"

    @pytest.mark.parametrize(
        ("field", "value"),
        [("cpf", 123), ("timezone", True)],
        ids=["numeric-cpf", "boolean-timezone"],
    )
    def test_rejects_incompatible_json_types(
        self, field: str, value: object, individual_payload: dict[str, str]
    ) -> None:
        payload = {**individual_payload, field: value}

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "QIT000001"
