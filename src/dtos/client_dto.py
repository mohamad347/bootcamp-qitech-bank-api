from datetime import datetime, timezone

from models import Client, CompanyClient, IndividualClient


class ClientDTO:
    """Projeções públicas dos snapshots de CLIENT da R02."""

    @staticmethod
    def individual_to_response(
        client: Client,
        status: str,
        individual_client: IndividualClient,
    ) -> dict:
        return {
            **ClientDTO._base_response(client, status),
            "cpf": individual_client.cpf,
            "full_name": individual_client.full_name,
            "birth_date": individual_client.birth_date.isoformat(),
        }

    @staticmethod
    def company_to_response(
        client: Client,
        status: str,
        company_client: CompanyClient,
    ) -> dict:
        return {
            **ClientDTO._base_response(client, status),
            "cnpj": company_client.cnpj,
            "legal_name": company_client.legal_name,
            "trade_name": company_client.trade_name,
        }

    @staticmethod
    def _base_response(client: Client, status: str) -> dict:
        return {
            "client_key": str(client.client_key),
            "client_type": client.client_type,
            "email": client.email,
            "timezone": client.timezone,
            "status": status,
            "created_at": ClientDTO._as_utc_isoformat(client.created_at),
            "updated_at": ClientDTO._as_utc_isoformat(client.updated_at),
        }

    @staticmethod
    def _as_utc_isoformat(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
