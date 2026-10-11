from connectors.rest_connector import RestConnector
from constants import ANALYSIS_PROVIDER_TIMEOUT, ANALYSIS_PROVIDER_URL


class ClientAnalysisConnector(RestConnector):
    def __init__(self) -> None:
        super().__init__(
            class_name=__name__,
            base_url=ANALYSIS_PROVIDER_URL,
            timeout=ANALYSIS_PROVIDER_TIMEOUT,
        )

    def analyze(self, client_key: str, client_type: str, document: str) -> dict:
        response = self.send(
            endpoint="/v1/client-analysis",
            method="POST",
            payload={
                "client_key": client_key,
                "client_type": client_type,
                "document": document,
            },
        )

        if response.status != 200:
            raise RuntimeError("Analysis Provider returned an unsuccessful status")

        if not isinstance(response.json, dict):
            raise RuntimeError("Analysis Provider returned an invalid JSON body")

        return response.json
