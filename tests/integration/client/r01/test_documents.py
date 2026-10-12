"""Cen?rios da R01 organizados por comportamento."""

from .support import *


class TestCreateClient:
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

    def test_rejects_cpf_with_invalid_check_digits(
        self, individual_payload: dict[str, str]
    ) -> None:
        individual_payload["cpf"] = "52998224726"

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "CLI0006"
        assert {"title", "description", "translation", "code"} <= set(
            response.response_json
        )

    def test_rejects_duplicate_cpf(
        self, individual_payload: dict[str, str]
    ) -> None:
        second_payload = {
            **individual_payload,
            "email": f"r01.pf.duplicate-cpf.{uuid4()}@example.com",
            "full_name": "Maria Teste",
        }

        first_response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        assert first_response.response_status == 201

        second_response = ClientRequisition.send(
            "POST",
            "/client",
            payload=second_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert second_response.response_status == 409
        assert second_response.response_json["code"] == "CLI0004"
        assert {"title", "description", "translation", "code"} <= set(
            second_response.response_json
        )

    def test_treats_masked_and_unmasked_cpf_as_same_document(
        self, individual_payload: dict[str, str]
    ) -> None:
        cpf_digits = individual_payload["cpf"].replace(".", "").replace("-", "")
        individual_payload["cpf"] = (
            f"{cpf_digits[:3]}.{cpf_digits[3:6]}.{cpf_digits[6:9]}-{cpf_digits[9:]}"
        )
        second_payload = {
            **individual_payload,
            "email": f"r01.pf.unmasked-cpf.{uuid4()}@example.com",
            "cpf": cpf_digits,
        }

        first_response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        assert first_response.response_status == 201

        second_response = ClientRequisition.send(
            "POST",
            "/client",
            payload=second_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert second_response.response_status == 409
        assert second_response.response_json["code"] == "CLI0004"
        assert {"title", "description", "translation", "code"} <= set(
            second_response.response_json
        )

    def test_rejects_cnpj_with_invalid_check_digit(
        self, company_payload: dict[str, str]
    ) -> None:
        valid_cnpj = company_payload["cnpj"]
        cnpj_digits = valid_cnpj.replace(".", "").replace("/", "").replace("-", "")
        invalid_last_digit = (int(cnpj_digits[-1]) + 1) % 10
        company_payload["cnpj"] = f"{cnpj_digits[:-1]}{invalid_last_digit}"

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=company_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "CLI0006"
        assert {"title", "description", "translation", "code"} <= set(
            response.response_json
        )

    def test_rejects_duplicate_company_cnpj(
        self, company_payload: dict[str, str]
    ) -> None:
        masked_cnpj = company_payload["cnpj"]
        second_payload = {
            **company_payload,
            "email": f"r01.company.duplicate-cnpj.{uuid4()}@example.com",
            "cnpj": masked_cnpj.replace(".", "").replace("/", "").replace("-", ""),
        }

        first_response = ClientRequisition.send(
            "POST",
            "/client",
            payload=company_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        assert first_response.response_status == 201

        second_response = ClientRequisition.send(
            "POST",
            "/client",
            payload=second_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert second_response.response_status == 409
        assert second_response.response_json["code"] == "CLI0005"
        assert {"title", "description", "translation", "code"} <= set(
            second_response.response_json
        )
