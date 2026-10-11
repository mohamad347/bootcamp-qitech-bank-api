from uuid import UUID

from connectors import ClientAnalysisConnector
from controllers.base_controller import BaseController
from models import ClientStatus
from repositories import ClientAnalysisRepository


class ClientAnalysisController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.client_analysis_repository = ClientAnalysisRepository(self.context)
        self.client_analysis_connector = ClientAnalysisConnector()

    def analyze(self, client_key: str) -> dict:
        analysis_data = self.client_analysis_repository.get_analysis_data(
            UUID(client_key)
        )

        if analysis_data["status"] != ClientStatus.PENDING:
            raise RuntimeError("Only a PENDING client can be analyzed")

        # A leitura inicial abre uma transação implícita. Como todos os dados
        # necessários já foram copiados para o dicionário, encerramos essa
        # transação antes de esperar pela chamada HTTP externa.
        self.session.rollback()

        provider_result = self.client_analysis_connector.analyze(
            client_key=analysis_data["client_key"],
            client_type=analysis_data["client_type"],
            document=analysis_data["document"],
        )

        if provider_result.get("decision") != "APPROVE":
            raise RuntimeError("The first R03 cycle only supports APPROVE")

        return {
            "client_key": analysis_data["client_key"],
            "status": ClientStatus.ACTIVE,
        }
