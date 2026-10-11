from datetime import datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

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


@pytest.fixture
def company_payload() -> dict[str, str]:
    return {
        "client_type": "COMPANY",
        "email": f"r01.company.{uuid4()}@example.com",
        "cnpj": RandomGenerator.generate_cnpj(),
        "legal_name": "Empresa Teste Ltda",
        "trade_name": "Empresa Teste",
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

    def test_rejects_timezone_outside_brazil(
        self, individual_payload: dict[str, str]
    ) -> None:
        individual_payload["timezone"] = "Europe/London"

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "CLI0008"
        assert {"title", "description", "translation", "code"} <= set(
            response.response_json
        )

    def test_rejects_timezone_alias_outside_allowlist(
        self, individual_payload: dict[str, str]
    ) -> None:
        individual_payload["timezone"] = "Brazil/East"

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 400
        assert response.response_json["code"] == "CLI0008"
        assert {"title", "description", "translation", "code"} <= set(
            response.response_json
        )

    def test_rejects_underage_individual(
        self, individual_payload: dict[str, str]
    ) -> None:
        timezone_name = individual_payload["timezone"]
        individual_payload["birth_date"] = datetime.now(
            ZoneInfo(timezone_name)
        ).date().isoformat()

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 422
        assert response.response_json["code"] == "CLI0007"
        assert {"title", "description", "translation", "code"} <= set(
            response.response_json
        )

    def test_accepts_individual_turning_18_today(
        self, individual_payload: dict[str, str]
    ) -> None:
        timezone_name = individual_payload["timezone"]
        today = datetime.now(ZoneInfo(timezone_name)).date()
        try:
            birth_date = today.replace(year=today.year - 18)
        except ValueError:
            pytest.skip("Não há aniversário de 18 anos nesta data civil.")
        individual_payload["birth_date"] = birth_date.isoformat()

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        if datetime.now(ZoneInfo(timezone_name)).date() != today:
            pytest.skip("A data civil mudou durante a requisição.")

        assert response.response_status == 201

    def test_rejects_individual_turning_18_tomorrow(
        self, individual_payload: dict[str, str]
    ) -> None:
        timezone_name = individual_payload["timezone"]
        today = datetime.now(ZoneInfo(timezone_name)).date()
        tomorrow = today + timedelta(days=1)
        try:
            birth_date = tomorrow.replace(year=tomorrow.year - 18)
        except ValueError:
            pytest.skip("Não há aniversário de 18 anos nesta data civil.")
        individual_payload["birth_date"] = birth_date.isoformat()

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        if datetime.now(ZoneInfo(timezone_name)).date() != today:
            pytest.skip("A data civil mudou durante a requisição.")

        assert response.response_status == 422
        assert response.response_json["code"] == "CLI0007"
        assert {"title", "description", "translation", "code"} <= set(
            response.response_json
        )

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

    def test_create_valid_company_client(self) -> None:
        payload = {
            "client_type": "COMPANY",
            "email": f"r01.company.valid.{uuid4()}@example.com",
            "cnpj": RandomGenerator.generate_cnpj(),
            "legal_name": "Empresa Teste Ltda",
            "trade_name": "Empresa Teste",
            "timezone": "America/Sao_Paulo",
        }

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 201

        response_body = response.response_json
        assert isinstance(response_body, dict)
        assert set(response_body) == {"client_key", "client_type", "status"}
        assert response_body["client_type"] == "COMPANY"
        assert response_body["status"] == "PENDING"
        assert isinstance(response_body["client_key"], str)
        assert isinstance(UUID(response_body["client_key"]), UUID)

    def test_create_company_with_unmasked_cnpj(self) -> None:
        cnpj = RandomGenerator.generate_cnpj()
        payload = {
            "client_type": "COMPANY",
            "email": f"r01.company.unmasked.{uuid4()}@example.com",
            "cnpj": cnpj.replace(".", "").replace("/", "").replace("-", ""),
            "legal_name": "Empresa Teste Ltda",
            "trade_name": "Empresa Teste",
            "timezone": "America/Sao_Paulo",
        }

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 201
        assert set(response.response_json) == {"client_key", "client_type", "status"}
        assert response.response_json["client_type"] == "COMPANY"
        assert response.response_json["status"] == "PENDING"
        assert isinstance(UUID(response.response_json["client_key"]), UUID)

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

    def test_create_company_without_trade_name(
        self, company_payload: dict[str, str]
    ) -> None:
        del company_payload["trade_name"]

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=company_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 201
        assert set(response.response_json) == {"client_key", "client_type", "status"}
        assert response.response_json["client_type"] == "COMPANY"
        assert response.response_json["status"] == "PENDING"
        assert isinstance(UUID(response.response_json["client_key"]), UUID)

    @pytest.mark.parametrize("trade_name", ["", "     "], ids=["empty", "whitespace"])
    def test_create_company_with_blank_trade_name(
        self, trade_name: str, company_payload: dict[str, str]
    ) -> None:
        company_payload["trade_name"] = trade_name

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=company_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 201
        assert set(response.response_json) == {"client_key", "client_type", "status"}
        assert response.response_json["client_type"] == "COMPANY"
        assert response.response_json["status"] == "PENDING"
        assert isinstance(UUID(response.response_json["client_key"]), UUID)

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
