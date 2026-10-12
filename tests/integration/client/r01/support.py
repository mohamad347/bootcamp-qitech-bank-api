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

__all__ = [name for name in globals() if not name.startswith("__")]
