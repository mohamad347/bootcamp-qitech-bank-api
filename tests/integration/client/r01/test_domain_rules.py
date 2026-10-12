"""Cen?rios da R01 organizados por comportamento."""

from .support import *


class TestCreateClient:
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

    def test_rejects_future_individual_birth_date(
        self, individual_payload: dict[str, str]
    ) -> None:
        timezone_name = individual_payload["timezone"]
        future_date = datetime.now(ZoneInfo(timezone_name)).date() + timedelta(days=365)
        individual_payload["birth_date"] = future_date.isoformat()

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=individual_payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )

        assert response.response_status == 422
        assert response.response_json["code"] == "CLI0007"
