from connectors.rest_connector import RestConnector
from constants import ANALYSIS_PROVIDER_TIMEOUT, ANALYSIS_PROVIDER_URL

MAX_REJECTION_REASON_LENGTH = 500


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

        decision = response.json.get("decision")
        if decision not in ("APPROVE", "REJECT"):
            raise RuntimeError("Analysis Provider returned an invalid decision")

        if decision == "APPROVE":
            return {
                "decision": decision,
                "reason": None,
            }

        reason = response.json.get("reason")
        if not isinstance(reason, str):
            raise RuntimeError("Analysis Provider returned REJECT without a reason")

        normalized_reason = reason.strip()
        if (
            not normalized_reason
            or len(normalized_reason) > MAX_REJECTION_REASON_LENGTH
        ):
            raise RuntimeError("Analysis Provider returned an invalid rejection reason")

        return {
            "decision": decision,
            "reason": normalized_reason,
        }
