from models import Client, ClientStatus


class ClientAnalysisDTO:
    """Traduz models para os dados usados e devolvidos pela R03."""

    @staticmethod
    def obj_to_analysis_data(client: Client, document: str) -> dict:
        """Copia do ORM os dados necessários durante a análise."""
        return {
            "client_key": str(client.client_key),
            "client_type": client.client_type,
            "document": document,
            "status": client.status.enumerator,
        }

    @staticmethod
    def obj_to_response(client: Client, status: ClientStatus) -> dict:
        """Monta o JSON público devolvido pela rota de análise."""
        return {
            "client_key": str(client.client_key),
            "status": status.enumerator,
        }
