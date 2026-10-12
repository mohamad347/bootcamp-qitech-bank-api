"""Cen?rios da R01 organizados por comportamento."""

from .support import *


class TestCreateClient:
    def test_rejects_duplicate_email(
        self, individual_payload: dict[str, str]
    ) -> None:
        second_cpf = RandomGenerator.generate_cpf()
        while second_cpf == individual_payload["cpf"]:
            second_cpf = RandomGenerator.generate_cpf()
        second_payload = {
            **individual_payload,
            "cpf": second_cpf,
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
        assert second_response.response_json["code"] == "CLI0003"
        assert {"title", "description", "translation", "code"} <= set(
            second_response.response_json
        )

    def test_treats_email_as_case_insensitive(
        self, individual_payload: dict[str, str]
    ) -> None:
        first_email = f"User.{uuid4().hex.upper()}@Example.COM"
        individual_payload["email"] = first_email

        second_cpf = RandomGenerator.generate_cpf()
        while second_cpf == individual_payload["cpf"]:
            second_cpf = RandomGenerator.generate_cpf()
        second_payload = {
            **individual_payload,
            "email": first_email.lower(),
            "cpf": second_cpf,
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
        assert second_response.response_json["code"] == "CLI0003"
        assert {"title", "description", "translation", "code"} <= set(
            second_response.response_json
        )

    def test_trims_outer_email_whitespace_before_uniqueness_check(
        self, individual_payload: dict[str, str]
    ) -> None:
        second_cpf = RandomGenerator.generate_cpf()
        while second_cpf == individual_payload["cpf"]:
            second_cpf = RandomGenerator.generate_cpf()
        second_payload = {
            **individual_payload,
            "email": f"  {individual_payload['email']}  ",
            "cpf": second_cpf,
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
        assert second_response.response_json["code"] == "CLI0003"
        assert {"title", "description", "translation", "code"} <= set(
            second_response.response_json
        )

    def test_rejects_duplicate_email_between_companies(
        self, company_payload: dict[str, str]
    ) -> None:
        second_cnpj = RandomGenerator.generate_cnpj()
        while second_cnpj == company_payload["cnpj"]:
            second_cnpj = RandomGenerator.generate_cnpj()
        second_payload = {**company_payload, "cnpj": second_cnpj}

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
        assert second_response.response_json["code"] == "CLI0003"
        assert {"title", "description", "translation", "code"} <= set(
            second_response.response_json
        )

    def test_rejects_duplicate_email_between_individual_and_company(
        self,
        individual_payload: dict[str, str],
        company_payload: dict[str, str],
    ) -> None:
        company_payload["email"] = individual_payload["email"]

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
            payload=company_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert second_response.response_status == 409
        assert second_response.response_json["code"] == "CLI0003"
        assert {"title", "description", "translation", "code"} <= set(
            second_response.response_json
        )

    def test_trims_company_email_before_uniqueness_check(
        self, company_payload: dict[str, str]
    ) -> None:
        second_cnpj = RandomGenerator.generate_cnpj()
        while second_cnpj == company_payload["cnpj"]:
            second_cnpj = RandomGenerator.generate_cnpj()
        second_payload = {
            **company_payload,
            "email": f"  {company_payload['email']}  ",
            "cnpj": second_cnpj,
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
        assert second_response.response_json["code"] == "CLI0003"
        assert {"title", "description", "translation", "code"} <= set(
            second_response.response_json
        )
