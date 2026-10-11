from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

from tests.utils import INTERNAL_TOKEN, RandomGenerator
from tests.utils.requisition import ClientRequisition


INDIVIDUAL_RESPONSE_FIELDS = {
    "client_key",
    "client_type",
    "email",
    "timezone",
    "status",
    "cpf",
    "full_name",
    "birth_date",
    "created_at",
    "updated_at",
}


def _assert_utc_timestamp(value: str) -> None:
    assert value.endswith("Z")

    parsed_value = datetime.fromisoformat(f"{value[:-1]}+00:00")
    assert parsed_value.utcoffset() == timedelta(0)


def test_get_individual_client_snapshot() -> None:
    email = f"R02.PF.{uuid4()}@Example.COM"
    cpf = RandomGenerator.generate_cpf()
    payload = {
        "client_type": "INDIVIDUAL",
        "email": f"  {email}  ",
        "cpf": cpf,
        "full_name": "  Joao R02  ",
        "birth_date": "2000-01-01",
        "timezone": "America/Manaus",
    }

    create_response = ClientRequisition.send(
        "POST",
        "/client",
        payload=payload,
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )
    assert create_response.response_status == 201

    client_key = create_response.response_json["client_key"]
    assert isinstance(UUID(client_key), UUID)

    get_response = ClientRequisition.send(
        "GET",
        f"/client/{client_key}",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    assert get_response.response_status == 200
    response_body = get_response.response_json
    assert isinstance(response_body, dict)
    assert set(response_body) == INDIVIDUAL_RESPONSE_FIELDS
    assert response_body["client_key"] == client_key
    assert response_body["client_type"] == "INDIVIDUAL"
    assert response_body["email"] == email.lower()
    assert response_body["timezone"] == payload["timezone"]
    assert response_body["status"] == "PENDING"
    assert response_body["cpf"] == cpf.replace(".", "").replace("-", "")
    assert response_body["full_name"] == "Joao R02"
    assert response_body["birth_date"] == date.fromisoformat(
        payload["birth_date"]
    ).isoformat()
    _assert_utc_timestamp(response_body["created_at"])
    _assert_utc_timestamp(response_body["updated_at"])
