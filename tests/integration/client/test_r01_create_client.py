from uuid import uuid4

from tests.utils import INTERNAL_TOKEN, RandomGenerator
from tests.utils.requisition import ClientRequisition


class TestCreateClient:
    def test_create_valid_individual_client(self):
        payload = {
            "client_type": "INDIVIDUAL",
            "email": f"r01.pf.valid.{uuid4()}@example.com",
            "cpf": RandomGenerator.generate_cpf(),
            "full_name": "Joao Teste",
            "birth_date": "2000-01-01",
            "timezone": "America/Sao_Paulo",
        }

        response = ClientRequisition.send(
            "POST",
            "/client",
            payload=payload,
            headers={"INTERNAL-TOKEN": INTERNAL_TOKEN},
        )
        assert response.response_status == 201
