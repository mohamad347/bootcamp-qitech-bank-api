"""Testes da R02: cen?rios organizados por comportamento."""

from .support import *


@pytest.mark.parametrize(
    "target_status",
    ["ACTIVE", "REJECTED", "INACTIVE"],
    ids=["active", "rejected", "inactive"],
)
def test_get_individual_client_snapshot_for_non_pending_status(
    target_status: str,
    api_database_engine: Engine,
) -> None:
    email = f"r02.status.{target_status.lower()}.{uuid4()}@example.com"
    cpf = RandomGenerator.generate_cpf()
    payload = {
        "client_type": "INDIVIDUAL",
        "email": email,
        "cpf": cpf,
        "full_name": "Cliente R02 ACTIVE",
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
    _prepare_client_status(
        api_database_engine,
        client_key,
        expected_email=email,
        target_status=target_status,
    )

    get_response = ClientRequisition.send(
        "GET",
        f"/client/{client_key}",
        headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
    )

    assert get_response.response_status == 200
    response_body = get_response.response_json
    assert set(response_body) == INDIVIDUAL_RESPONSE_FIELDS
    assert response_body["client_key"] == client_key
    assert response_body["client_type"] == "INDIVIDUAL"
    assert response_body["email"] == email
    assert response_body["timezone"] == payload["timezone"]
    assert response_body["status"] == target_status
    assert response_body["cpf"] == cpf.replace(".", "").replace("-", "")
    assert response_body["full_name"] == payload["full_name"]
    assert response_body["birth_date"] == payload["birth_date"]
    _assert_utc_timestamp(response_body["created_at"])
    _assert_utc_timestamp(response_body["updated_at"])
