from uuid import UUID

from connectors import ClientAnalysisConnector
from controllers.base_controller import BaseController
from dtos import ClientAnalysisDTO
from errors import ClientNotFound, InvalidClientStatus, InvalidParameter
from models import ClientStatus, ClientStatusEvent
from repositories import ClientAnalysisRepository


class ClientAnalysisController(BaseController):
    def __init__(self) -> None:
        super().__init__(__name__)
        self.client_analysis_repository = ClientAnalysisRepository(self.context)
        self.client_analysis_connector = ClientAnalysisConnector()

    def analyze(self, client_key: str) -> dict:
        try:
            parsed_client_key = UUID(client_key)
        except ValueError:
            raise InvalidParameter("client_key must be a valid UUID.") from None

        analysis_source = self.client_analysis_repository.get_analysis_source(
            parsed_client_key
        )
        if analysis_source is None:
            raise ClientNotFound(client_key)

        client_snapshot, document = analysis_source
        analysis_data = ClientAnalysisDTO.obj_to_analysis_data(
            client_snapshot,
            document,
        )

        if analysis_data["status"] != ClientStatus.PENDING:
            raise InvalidClientStatus(
                current_status=analysis_data["status"],
                required_status=ClientStatus.PENDING,
            )

        # A leitura inicial abre uma transação implícita. Como todos os dados
        # necessários já foram copiados para o dicionário, encerramos essa
        # transação antes de esperar pela chamada HTTP externa.
        self.session.rollback()

        provider_result = self.client_analysis_connector.analyze(
            client_key=analysis_data["client_key"],
            client_type=analysis_data["client_type"],
            document=analysis_data["document"],
        )

        target_status_enumerator, status_change_reason = (
            self._translate_provider_decision(provider_result)
        )

        # A etapa crítica começa somente depois da chamada externa. O lock
        # impede duas transações de alterarem este cliente ao mesmo tempo.
        client = self.client_analysis_repository.get_by_client_key_for_update(
            parsed_client_key
        )

        if client.status.enumerator != ClientStatus.PENDING:
            raise InvalidClientStatus(
                current_status=client.status.enumerator,
                required_status=ClientStatus.PENDING,
            )

        pending_status = client.status
        target_status = self.client_analysis_repository.get_status(
            target_status_enumerator
        )
        self.client_analysis_repository.apply_status_change(
            client=client,
            from_status=pending_status,
            to_status=target_status,
            actor_type=ClientStatusEvent.INTERNAL,
            reason=status_change_reason,
        )

        response_data = ClientAnalysisDTO.obj_to_response(client, target_status)
        self.session.commit()

        return response_data

    @staticmethod
    def _translate_provider_decision(
        provider_result: dict,
    ) -> tuple[str, str | None]:
        """Converte a decisão externa na transição de status do domínio."""
        decision = provider_result.get("decision")
        if decision == "APPROVE":
            return ClientStatus.ACTIVE, None
        if decision == "REJECT":
            return ClientStatus.REJECTED, provider_result.get("reason")

        raise RuntimeError("Analysis Provider returned an invalid decision")
