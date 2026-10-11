from uuid import UUID

from database import Context
from models import Client, CompanyClient, IndividualClient


class ClientAnalysisRepository:
    def __init__(self, context: Context) -> None:
        self.session = context.db_session

    def get_analysis_data(self, client_key: UUID) -> dict:
        client = (
            self.session.query(Client)
            .filter(Client.client_key == client_key)
            .one()
        )

        if client.client_type == "INDIVIDUAL":
            profile = (
                self.session.query(IndividualClient)
                .filter(IndividualClient.client_id == client.id)
                .one()
            )
            document = profile.cpf
        else:
            profile = (
                self.session.query(CompanyClient)
                .filter(CompanyClient.client_id == client.id)
                .one()
            )
            document = profile.cnpj

        return {
            "client_key": str(client.client_key),
            "client_type": client.client_type,
            "document": document,
            "status": client.status.enumerator,
        }
