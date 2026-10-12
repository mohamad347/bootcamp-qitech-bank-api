"""Cen?rios da R01 organizados por comportamento."""

from .support import *


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

    def test_accepts_email_at_254_character_limit(
        self, individual_payload: dict[str, str]
    ) -> None:
        local_part = f"{uuid4().hex}{'a' * 32}"
        individual_payload["email"] = (
            f"{local_part}@{'b' * 63}.{'c' * 63}.{'d' * 53}.example"
        )
        assert len(individual_payload["email"]) == 254

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 201

    def test_accepts_company_names_at_200_character_limit(
        self, company_payload: dict[str, str]
    ) -> None:
        company_payload["legal_name"] = "L" * 200
        company_payload["trade_name"] = "T" * 200

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=company_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 201
